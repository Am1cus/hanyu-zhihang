"""Non-destructive real HTTP acceptance of all eligible dataset_v2 flights.

Uses a fresh output directory, keeps every run, and labels repetitions as
engineering tests, not new independent model confirmation. No model fitting.
"""
import argparse
import contextlib
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

if __package__ in (None, ""):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from Phase4 import replay_airsim as replay
from Phase4.energy_v3_service import MODEL


def read_events(base, run):
    after=-1;events=[]
    while True:
        page=replay.get_json(f"{base}/api/runs/{run}/events?afterSeq={after}&limit=1000")
        events.extend(page)
        if len(page)<1000: return events
        after=page[-1]["telemetry"]["sampleSeq"]


def distribution(values):
    if not values: return {"n":0,"mean_ms":None,"p99_ms":None,"max_ms":None}
    return {"n":len(values),"mean_ms":float(np.mean(values)),"p99_ms":float(np.percentile(values,99)),"max_ms":float(max(values))}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True,help="New directory; report is never overwritten")
    parser.add_argument("--backend-url",default="http://127.0.0.1:8080")
    args=parser.parse_args()
    if args.output.exists(): parser.error("输出目录已存在，请使用新的目录")
    args.output.mkdir(parents=True)
    started=time.time();base=args.backend_url.rstrip("/")
    flights=replay.load_flights(args.source)
    report={"scope":"engineering_replay_not_independent_model_confirmation","model":MODEL,
            "source_sha256":hashlib.sha256(args.source.read_bytes()).hexdigest(),"flights":[],"excluded":{},
            "all_passed":False,"backend_url":base}
    network=[];inference=[];ai_http=[]
    original_post=replay.post_json
    try:
        for flight,frame in flights:
            meta=frame.attrs.get("v3_provenance")
            if not meta: raise ValueError("Only manifest-audited V3 data supported")
            if meta["quarantine_reason"]:
                report["excluded"][flight]=meta["quarantine_reason"];continue
            payloads=[]
            def measured_post(url,payload):
                begin=time.perf_counter()
                result=original_post(url,payload)
                if url.endswith("/api/telemetry"):
                    network.append((time.perf_counter()-begin)*1000)
                    payloads.append(payload)
                return result
            replay.post_json=measured_post
            config=replay.build_parser().parse_args([str(args.source),"--flight-id",flight,"--speed","0","--backend-url",base])
            with (args.output/f"{flight}.log").open("w") as log,contextlib.redirect_stdout(log):
                run=replay.replay(config,flight,frame,replay.resolve_columns(frame))
            replay.post_json=original_post
            run_id=run["runId"];events=read_events(base,run_id)
            assert len(events)==len(payloads)==run["expectedSamples"]
            valid=[e for e in events if e["prediction"]["valid"]]
            eligible=[e for e in events if e["prediction"]["window_samples"]==30]
            assert len(valid)==len(eligible)>0, "Eligible input did not yield a valid candidate prediction"
            assert all(e["prediction"]["model_version"]==MODEL for e in events)
            assert all(e["prediction"]["project_acceptance_passed"] is False for e in valid)
            assert all(e["prediction"]["validated_on_real_data"] is False for e in valid)
            verified=[e for e in events if e["verification"]["status"]=="verified"]
            assert verified, "No arrived labels"
            methods=run["baselineMetrics"]
            assert len({v["count"] for v in methods.values()})==1
            assert methods["lstm"]["count"]==len(verified)
            for e in valid:
                inference.append(e["prediction"]["inference_time_ms"])
                ai_http.append(e["prediction"]["ai_http_roundtrip_ms"])
            # An identical retry after completion must not append a second record.
            before=events
            original_post(base+"/api/telemetry",payloads[29])
            assert replay.get_json(f"{base}/api/runs/{run_id}")["sampleCount"]==len(events)
            assert read_events(base,run_id)==before, "An identical retry changed archived predictions"
            recheck=original_post(f"{base}/api/runs/{run_id}/recheck?sampleSeq={valid[0]['telemetry']['sampleSeq']}",{})
            assert recheck["data"]["consistent"] is True
            assert read_events(base,run_id)==before, "A recheck overwrote original predictions"
            (args.output/f"{flight}-events.json").write_text(json.dumps(events,ensure_ascii=False,allow_nan=False),encoding="utf-8")
            item={"flight_id":flight,"run_id":run_id,"samples":len(events),"valid_predictions":len(valid),
                  "verified_predictions":len(verified),"baseline_metrics":methods,
                  "evaluation_role":meta["evaluation_role"],"duplicate_retry_preserved":True,"recheck_consistent":True}
            report["flights"].append(item)
            print(f"{flight}: {len(events)} saved, {len(valid)} inferred, {len(verified)} verified; retry/recheck OK",flush=True)
        assert len(report["flights"])>=20,"Fewer than 20 eligible flight scenarios"
        report["all_passed"]=True
    except BaseException as error:
        report["error"]=str(error)
        raise
    finally:
        replay.post_json=original_post
        report.update(telemetry_http_roundtrip=distribution(network),ai_http_roundtrip=distribution(ai_http),
                      inference_internal=distribution(inference),elapsed_seconds=time.time()-started)
        # Threshold conclusions separate correctness from performance and UI rendering.
        report["telemetry_mean_le_150ms"]=bool(network and np.mean(network)<=150)
        report["ai_http_p99_le_100ms"]=bool(ai_http and np.percentile(ai_http,99)<=100)
        report["browser_update_latency_verified"]=False
        (args.output/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k not in {"flights","excluded"}},ensure_ascii=False,indent=2))


if __name__=="__main__":main()
