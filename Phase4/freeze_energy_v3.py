"""Freeze a transparently post-selected project-method candidate, not a pass.

No training and no change to the original pre-test selection or evaluation.
Exported runtime must reproduce EVERY archived retained-flight prediction.
"""
import argparse
import io
import json
import shutil
import tempfile
import time
from pathlib import Path

import joblib
import numpy as np
import torch

from capacity_v3 import FEATURE_SETS, build_windows, group_metrics, predict_network, read_dataset, sha256, subset, write_json
from final_energy_runtime import CONTRACT, RAW_FIELDS, FrozenEnergyPredictor
from train_capacity_v3 import check_protocol, load_network

CANDIDATE = "residual_core32"


def quantization_check(root, selection, frames, protocol):
    torch.backends.quantized.engine="qnnpack"
    float_models=[load_network(root,CANDIDATE,r) for r in selection["final_models"][CANDIDATE]]
    quantized=[(torch.ao.quantization.quantize_dynamic(m,{torch.nn.LSTM},dtype=torch.qint8),s,c,r)
               for m,s,c,r in float_models]
    result={"default_precision":"FP32", "qnnpack_int8_deployment":False,
            "scope":"local CPU, batch=1, not edge hardware or end-to-end service",
            "why_fp32":"Already small and below latency budget; INT8 not selected by tiny test-MAPE fluctuations",
            "groups":{}}
    for group in ("test","extra"):
        data=build_windows(frames,protocol["splits"][group]); values={}
        for label,models in (("fp32",float_models),("int8",quantized)):
            pred=np.mean([predict_network(m,s,c,data,r,1) for m,s,c,r in models],axis=0)
            values[label]=pred
            result["groups"].setdefault(group,{})[label]=group_metrics(data,pred)
        result["groups"][group]["maximum_output_difference_mah"]=float(np.max(np.abs(values["fp32"]-values["int8"]))*1000)
    for label,models in (("fp32",float_models),("int8",quantized)):
        sizes=[]
        for model,*_ in models:
            buffer=io.BytesIO();torch.save(model.state_dict(),buffer);sizes.append(buffer.tell())
        durations=[];one=subset(data,slice(0,1))
        for k in range(320):
            start=time.perf_counter()
            np.mean([predict_network(m,s,c,one,r,1) for m,s,c,r in models],axis=0)
            if k>=20:durations.append((time.perf_counter()-start)*1000)
        result[label]={"state_dict_bytes":sum(sizes), "median_ms":float(np.median(durations)),
                       "p99_ms":float(np.percentile(durations,99)), "n":len(durations)}
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment",type=Path,default=Path(__file__).parent/"experiments/capacity_v3_20260908")
    parser.add_argument("--output",type=Path,default=Path(__file__).parent/"releases/energy_residual_lstm_v3_rc1")
    args=parser.parse_args();root=args.experiment.resolve();target=args.output.resolve()
    if target.exists():raise ValueError("Frozen candidate already exists; never overwrite")
    protocol=check_protocol(root)
    selection=json.loads((root/"selection.json").read_text())
    opened=json.loads((root/"TEST_OPENED.json").read_text())
    if opened["selection_sha256"]!=sha256(root/"selection.json"):
        raise ValueError("Original selection changed after test exposure")
    evaluation=json.loads((root/"evaluation.json").read_text())
    archived=json.loads((root/"heldout_predictions.json").read_text())
    frames,_,_=read_dataset(protocol["source"])
    target.parent.mkdir(parents=True,exist_ok=True)
    work=Path(tempfile.mkdtemp(prefix=".energy-v3-build-",dir=target.parent))
    members=selection["final_models"][CANDIDATE]
    for member in members:
        src=root/"models"/member["file"]
        if sha256(src)!=member["sha256"]:raise ValueError("Source member changed")
        shutil.copy2(src,work/member["file"])
    scaler_path=root/"models"/f"{CANDIDATE}_scaler.joblib"
    if sha256(scaler_path)!=selection["artifact_sha256"][scaler_path.name]:
        raise ValueError("Source scaler changed")
    scaler=joblib.load(scaler_path)
    write_json(work/"scaler.json",{"features":FEATURE_SETS["core"],"mean":scaler.mean_.tolist(),
             "scale":scaler.scale_.tolist(),"source_sha256":sha256(scaler_path)})
    shutil.copy2(Path(__file__).with_name("final_energy_runtime.py"),work/"runtime.py")
    train_rows=np.concatenate([frames[f][FEATURE_SETS["core"]].dropna().to_numpy() for f in protocol["splits"]["train"]])
    ranges={f:{"min":float(train_rows[:,i].min()),"max":float(train_rows[:,i].max())}
            for i,f in enumerate(FEATURE_SETS["core"])}
    manifest={
        "model_version":"energy_residual_lstm_v3_rc1", "frozen_local":time.strftime("%Y-%m-%d %H:%M:%S%z"),
        "project_method_choice":"motion-feature residual LSTM, 3-seed FP32 ensemble",
        "candidate":CANDIDATE, "research_status":"post_selected_candidate_pending_independent_confirmation",
        "original_preselected_candidate":selection["selected_lstm"],
        "original_promotion_gate_passed":evaluation["promotion_eligible"],
        "post_selection_disclosure":"Chosen after inspecting all fixed-candidate test/extra results; old test is exploratory for this decision, not new confirmation",
        "project_acceptance_passed":False,"validated_on_real_data":False,"online_deployment_changed":False,
        "architecture":{"input_features":6,"lookback_seconds":30,"hidden_size":32,"layers":1,
                        "members":3,"parameters_per_member":6209,"precision":"FP32"},
        "features":FEATURE_SETS["core"],"training_feature_ranges":ranges,
        "output":"mean(history_charge_drop_10s * exp(each_LSTM_output)); no clipping/calibration/smoothing",
        "target":"difference of mean charge in two complete bins ten seconds apart, Ah",
        "sampling_contract":CONTRACT,"supported_data_domain":"AIRSIM_FORMULA_BATTERY",
        "excluded_claims":["SOH","battery aging capacity","remaining flight time","remaining range","validated extreme-cold real flights","A* savings"],
        "members":members,"source_dataset_sha256":protocol["source_sha256"],
        "source_protocol_sha256":sha256(root/"protocol.json"),"source_selection_sha256":sha256(root/"selection.json"),
        "source_evaluation_sha256":sha256(root/"evaluation.json"),
        "artifact_sha256":{p.name:sha256(p) for p in sorted(work.iterdir())}}
    write_json(work/"manifest.json",manifest)
    write_json(work/"RELEASE_LOCK.json",{"manifest_sha256":sha256(work/"manifest.json")})
    predictor=FrozenEnergyPredictor(work)
    timing=[];max_error=0;records=[];range_counts={}
    for row in archived:
        flight=row["flight_id"];at=row["prediction_available_at_s"]
        window=frames[flight][frames[flight].available_at_s<=at].tail(30)
        samples=window[RAW_FIELDS].to_dict("records")
        for sample in samples:sample["flight_id"]=flight
        prediction=predictor.predict(samples,sampling_contract=CONTRACT,data_source="AIRSIM_FORMULA_BATTERY")
        if not prediction["valid"]:raise ValueError(f"Exported runtime failed: {flight} {at} {prediction}")
        delta=abs(prediction["predicted_consumption_ah"]-row[CANDIDATE])
        if delta>1e-7:raise ValueError(f"Export changed prediction by {delta} Ah")
        max_error=max(max_error,delta)
        timing.append(prediction["inference_time_ms"])
        for f in prediction["outside_training_range_features"]:range_counts[f]=range_counts.get(f,0)+1
        records.append({"flight_id":flight,"available_at_s":at,"consumption_ah":prediction["predicted_consumption_ah"],"difference_from_archived_ah":delta})
        if flight=="F022" and at==60:
            write_json(work/"example_request.json",{"samples":samples,"sampling_contract":CONTRACT,"data_source":"AIRSIM_FORMULA_BATTERY"})
            write_json(work/"example_response.json",prediction)
    reproduction={"windows_reproduced":len(records),"maximum_absolute_difference_ah":max_error,
        "latency_scope":"exported standalone runtime incl. validation, feature derivation, scaling, three LSTMs; no network",
        "median_ms":float(np.median(timing[20:])),"p99_ms":float(np.percentile(timing[20:],99)),
        "training_range_warning_window_counts":range_counts,
        "frozen_weights_bytes":sum((work/r["file"]).stat().st_size for r in members),
        "all_valid":True,"verification_is_reproduction_not_independent_accuracy_validation":True}
    write_json(work/"runtime_verification.json",reproduction)
    write_json(work/"runtime_reproduction.json",records)
    quantization=quantization_check(root,selection,frames,protocol)
    write_json(work/"quantization_comparison.json",quantization)
    write_json(work/"confirmation_protocol.json",{
        "status":"prospective_proposal_no_confirmation_data_received",
        "frozen_release_manifest_sha256":sha256(work/"manifest.json"),
        "old_protocol_and_failed_gate_remain_unchanged":True,
        "purpose":"practical utility confirmation, not a claim of superiority to every ML method or original whole-project acceptance",
        "recommended_new_flights":24,"matrix":{"ambient_temperatures_c":[0,-10,-20,-30],
            "tracks":["cruise","variable","low_alt"],"new_seeds_per_cell":2},
        "before_collection":["provide collector and formula-battery code/parameters/hash", "freeze independent wind/payload schedules, avoiding the old fixed pairing", "confirm airborne/landed state and actual source-clock dt"],
        "must_not_reuse":{"zip_sha256":protocol["source_sha256"],"raw_sha256":[m["raw_sha256"] for m in protocol["metadata"].values()]},
        "no_fitting_or_selection_on_confirmation":True,
        "fixed_comparators":["history_10s","mean_current_20s","tree_residual_l7_i120","tree_residual_l15_i120"],
        "proposed_utility_criteria_not_original_acceptance":{
            "flight_macro_mape_pct_max":5,"relative_improvement_over_history_and_mean20_pct_min":15,
            "macro_mape_disadvantage_vs_each_fixed_tree_percentage_points_max":0.3,
            "minimum_flights_beating_history":18,"local_runtime_p99_ms_max":100},
        "report_all_failures_and_conditions":True,"independent_real_cold_battery_validation_still_required":True})
    names=["history_10s","current_10s","mean_current_20s","tree_residual_l7_i120","tree_residual_l15_i120","direct_full32",CANDIDATE]
    lines=["# 结题主模型方案：运动特征驱动的残差 LSTM", "", "日期：2026-09-09。版本：energy_residual_lstm_v3_rc1。", "",
        "## 选型结论", "", "选择 residual_core32 的三个固定种子 FP32 集成作为后续结题主模型方案；方法和权重已经冻结。**这是待独立确认的候选，不是已经通过项目最终验收。**", "",
        "原实验预先选中 direct_full32，但其未通过严格推广门槛。此处是在看过完整对照结果后作出的工程选型，原 selection.json、evaluation.json 和失败结论均保留；不能把旧测试集重新称为盲测。", "",
        "## 为什么选择它", "", "- 6 类序列特征：电流、风速、水平速度、垂直速度、相对气流速度和沿运动方向风分量。每个网络单层 32 隐单元，6,209 个参数。",
        "- 历史耗电给出参考量，LSTM 学习未来耗电相对参考量的变化；输出不是历史延续的原样复制，也没有事后直线纠正。",
        "- 7 个保留架次都优于历史延续；尤其动态飞行明显改善。主测试组与开发集预选树模型基本相当，补充组更好；不是宣称胜过所有树模型。",
        "- 不采用绝对高度，避免依靠某个固定飞行高度作为预测捷径。现有对照不能单独证明某一特征的因果作用。",
        "- 三个种子等权集成，不从测试结果挑选一个好种子。已保留单模型结果，不能把集成结果说成单个 LSTM 的性能。", "",
        "## 同口径结果（探索性）", "", "下表是未来 10 秒耗电量的窗口 MAPE，不是整块电池容量的误差，也不是预测准确率。", "",
        "| 方法 | 主测试 3 架次 / 612 窗口 | 补充 4 架次 / 1,252 窗口 |", "|---|---:|---:|"]
    for n in names:
        a,b=(evaluation["groups"][g]["methods"][n] for g in ("test","extra"))
        lines.append(f"| {n} | {a['mape_pct']:.3f}% | {b['mape_pct']:.3f}% |")
    lines += ["", "逐架次：", "", "| 架次 | 历史延续 MAPE | 残差 LSTM MAPE | 残差 LSTM MAE |", "|---|---:|---:|---:|"]
    for group in ("test","extra"):
        m=evaluation["groups"][group]["methods"]
        for f in evaluation["groups"][group]["flights"]:
            v=m[CANDIDATE]["per_flight"][f]
            lines.append(f"| {f} | {m['history_10s']['per_flight'][f]['mape_pct']:.3f}% | {v['mape_pct']:.3f}% | {v['mae_mah']:.3f} mAh |")
    lines += ["", "## 实际交付与速度", "",f"- 三个原始权重文件总计 {reproduction['frozen_weights_bytes']/1024:.1f} KiB；另含标定参数与独立 runtime.py。无需训练代码或 sklearn 即可推理（需要 numpy、torch）。",
        f"- 独立运行时已逐一复算全部 {len(records)} 个保留窗口，与原记录最大差 {max_error:.3g} Ah。P99 {reproduction['p99_ms']:.3f} ms，包含输入检查和特征计算，不含网络/数据库/网页。",
        f"- 同条件诊断 FP32 P99 {quantization['fp32']['p99_ms']:.3f} ms；INT8 P99 {quantization['int8']['p99_ms']:.3f} ms。默认保留 FP32；INT8 的细微误差变化不作为选型依据。尚未在树莓派验证。", "",
        "## 如何运行", "", "在 learn 目录执行（只读取请求，不修改后台）：", "", "```sh",
        ".venv/bin/python Phase4/releases/energy_residual_lstm_v3_rc1/runtime.py --request Phase4/releases/energy_residual_lstm_v3_rc1/example_request.json", "```", "",
        "样本必须是已完成的一秒平均桶，available_at_s 为桶右边界。不能直接传交付包的就近取样 1Hz CSV，不能混架次、插补缺秒或让未来数据进入输入。example_request.json 只含预测前的 30 秒，没有未来标签。", "",
        "## 距离真正结题还差什么", "", "1. 请仿真同学提供采集与电池模型代码，独立补采新 seed 数据；建议 4 温度 × 3 任务 × 2 seed = 24 架次，具体条件在采集前冻结。已有 7 架次不能再作为最终确认集。",
        "2. 用本目录锁定的原权重执行一次独立确认，报告历史估算、20 秒电流均值和两个固定树模型对照。confirmation_protocol.json 的指标是后续实用性确认建议，不会把旧失败门槛追溯改成通过。",
        "3. 再接入网页做 20 场景全链路验收；当前网站仍使用原 V2，本次未切换在线模型。",
        "4. 对照获批计划书另补真实低温电池、剩余航程、规划与目标边缘硬件验证，或经导师/学校批准调整范围。", "",
        "## 研究边界", "", "这是一种短期飞行耗电预测方法，不是已经验证的低温容量衰减模型。所选网络没有直接输入环境/电池温度；这些变量在本次候选中没有带来更稳定的结果，不能宣称已学习低温电化学机理。所有电池标签仍由公式生成。", "",
        "如果后续独立确认不如简单方法，应如实报告并调整方案，不继续在确认集上追分。", ""]
    (work/"MODEL_DECISION.md").write_text("\n".join(lines),encoding="utf-8")
    write_json(work/"DELIVERY_LOCK.json",{"evidence_sha256":{p.name:sha256(p) for p in sorted(work.iterdir())}})
    work.rename(target)
    print(json.dumps({"frozen_release":str(target),"candidate":CANDIDATE,"verification":reproduction,
                      "final_acceptance_passed":False},ensure_ascii=False,indent=2))


if __name__=="__main__":main()
