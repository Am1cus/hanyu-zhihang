"""Controlled fault-injection tests on the agent-started local demo only.

The original ZIP and saved runs stay unchanged. New runs are explicitly marked
engineering_fault_injection. The supplied AI process is always resumed.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from datetime import datetime,timedelta

if __package__ in (None,""): sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from Phase4.replay_airsim import get_json,post_json
from Phase4.accept_energy_v3 import read_events


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--ai-pid",type=int,required=True)
    parser.add_argument("--backend-url",default="http://127.0.0.1:8080")
    args=parser.parse_args();base=args.backend_url.rstrip("/")
    if args.output.exists(): parser.error("输出文件已存在")
    command=subprocess.check_output(["ps","-p",str(args.ai_pid),"-o","command="],text=True)
    if "uvicorn Phase3.inference_api:app" not in command: parser.error("PID不是指定的本机AI演示进程")
    batch=json.loads((args.batch/"report.json").read_text())
    entry=next(x for x in batch["flights"] if x["flight_id"]=="F022")
    source=get_json(f"{base}/api/runs/{entry['run_id']}")
    original=read_events(base,entry["run_id"])
    report={"scope":"controlled_fault_injection_not_new_AirSim_flights","checks":{},"runs":[]}

    def create(name,count):
        request={k:source[k] for k in ("flightId","droneId","droneCode","dataSource","sourceLabel","sourceSha256","preprocessingVersion","configuration")}
        request=copy.deepcopy(request);request["expectedSamples"]=count
        request["sourceLabel"]+=" / fault injection: "+name
        request["configuration"].update(fault_injection=name,evaluation_role="engineering_fault_injection",independent_confirmation=False)
        run=post_json(base+"/api/runs",request)["data"];report["runs"].append(run["runId"])
        return run

    def sample(run,index):
        row=copy.deepcopy(original[index]["telemetry"])
        for key in ("id","createTime","payloadSha256"): row.pop(key,None)
        row["runId"]=run["runId"]
        row["collectTime"]=(datetime.fromisoformat(run["collectStartTime"])+timedelta(seconds=row["sourceTimeS"])).isoformat()
        return row

    def send(row):
        assert post_json(base+"/api/telemetry",row)["data"] is True

    def finish(run,interrupted=False):
        post_json(base+"/api/runs/"+run["runId"]+"/finish",{"status":"INTERRUPTED" if interrupted else "COMPLETED"})

    def reject(row,code):
        try: send(row)
        except RuntimeError as error:
            assert f"HTTP {code}" in str(error);return
        raise AssertionError("Invalid request unexpectedly accepted")

    try:
        run=create("missing_windX_at_seq30_then_recovery",61)
        for i in range(61):
            row=sample(run,i)
            if i==30: row.pop("windX")
            send(row)
        events=read_events(base,run["runId"])
        assert events[29]["prediction"]["valid"] and not events[30]["prediction"]["valid"]
        assert events[30]["prediction"]["predicted_consumption_Ah"] is None
        assert not events[59]["prediction"]["valid"] and events[60]["prediction"]["valid"]
        report["checks"]["missing_vector_and_30s_recovery"]=True;finish(run)

        run=create("skip_seq35_no_interpolation",75)
        for i in range(75):
            if i!=35: send(sample(run,i))
        events=read_events(base,run["runId"]);by_seq={e["telemetry"]["sampleSeq"]:e for e in events}
        assert by_seq[29]["verification"]["status"]=="invalid_target"
        assert not by_seq[64]["prediction"]["valid"] and by_seq[65]["prediction"]["valid"]
        reject(sample(run,35),409)
        wrong=sample(run,29);wrong["voltage"]+=.1;reject(wrong,409)
        wrong=sample(run,29);wrong["flightId"]="wrong_flight";reject(wrong,400)
        assert read_events(base,run["runId"])==events
        report["checks"]["gap_future_label_conflict_cross_flight_preserve_archive"]=True;finish(run,True)

        run=create("explicit_sensor_fault_temp_drop_at10_SOC19_at20",41)
        for i in range(41):
            row=sample(run,i);row["envTemperature"]=0 if i<10 else -30;row["batteryLevel"]=70 if i<20 else 19
            send(row)
        # Read persisted warning records through the normal UI API.
        warnings=get_json(base+"/api/dashboard/latest-warnings")
        types={w["warningType"] for w in warnings if w.get("runId")==run["runId"]}
        assert {"TEMPERATURE","BATTERY"}<=types
        report["checks"]["temperature_SOC_threshold_warnings"]=True;finish(run)

        run=create("AI_process_paused_for_seq29_then_resumed",41)
        for i in range(29):send(sample(run,i))
        os.kill(args.ai_pid,signal.SIGSTOP)
        try: send(sample(run,29))
        finally: os.kill(args.ai_pid,signal.SIGCONT)
        unavailable=read_events(base,run["runId"])[29]["prediction"]
        assert unavailable["valid"] is False and unavailable["predicted_consumption_Ah"] is None
        assert unavailable["reason"]=="ai_service_unavailable"
        for i in range(30,41):send(sample(run,i))
        events=read_events(base,run["runId"])
        assert events[30]["prediction"]["valid"]
        assert events[29]["prediction"]==unavailable
        report["checks"]["AI_offline_save_recovery_no_retroactive_replacement"]=True;finish(run)
        assert read_events(base,entry["run_id"])==original
        for flight in batch["flights"]:
            saved=json.loads((args.batch/f"{flight['flight_id']}-events.json").read_text())
            assert read_events(base,flight["run_id"])==saved
        report["checks"]["original_20_flight_archive_unchanged"]=True
        report["all_passed"]=True
    except BaseException as error:
        report["all_passed"]=False;report["error"]=str(error);raise
    finally:
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=="__main__":main()
