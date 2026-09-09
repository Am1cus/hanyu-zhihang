"""Render immutable test outputs; never fit, smooth, or alter predictions."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from capacity_v3 import write_json


def flight_bootstrap(method, reference):
    flights = sorted(method["per_flight"])
    delta = np.array([reference["per_flight"][f]["mape_pct"]-method["per_flight"][f]["mape_pct"] for f in flights])
    rng = np.random.default_rng(42)
    means = delta[rng.integers(len(delta),size=(5000,len(delta)))].mean(axis=1)
    return {"independent_flights": len(flights), "macro_mape_difference_pp": float(delta.mean()),
            "paired_flight_bootstrap_95pct_interval_pp": np.percentile(means,[2.5,97.5]).tolist(),
            "warning": "Very few flights; descriptive interval, not a population-level significance claim"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    args = parser.parse_args(); root = args.experiment
    report = json.loads((root/"evaluation.json").read_text())
    rows = json.loads((root/"heldout_predictions.json").read_text())
    protocol = json.loads((root/"protocol.json").read_text())
    selection = json.loads((root/"selection.json").read_text())
    dev = json.loads((root/"development/lstm_search.json").read_text())
    name, baseline = report["selected_lstm"], report["selected_comparator"]
    config = dev[name]["config"]
    # Correct only a descriptive field in the initially generated manifest.
    # Training, selection, model hashes and every test prediction remain immutable.
    transform = ("history_10s * exp(learned_log_residual), no post-hoc correction" if config["residual"]
                 else "training_geometric_mean_consumption * exp(LSTM_output), no history anchor or post-hoc correction")
    manifest_path = root/"candidate_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest["prediction_transform"] != transform:
        write_json(root/"metadata_erratum.json", {
            "field": "candidate_manifest.prediction_transform",
            "initial_text": manifest["prediction_transform"], "corrected_text": transform,
            "reason": "initial exporter described all architectures as residual; actual selected checkpoint is direct",
            "training_selection_and_predictions_changed": False})
        manifest["prediction_transform"] = transform
        write_json(manifest_path, manifest)
    plt.rcParams.update({"font.family": "DejaVu Sans", "axes.spines.top": False,
                         "axes.spines.right":False, "font.size":10, "figure.facecolor":"#faf9f5", "axes.facecolor":"#faf9f5"})
    for group in ("test","extra"):
        flights = report["groups"][group]["flights"]
        figure, axes = plt.subplots(len(flights),1,figsize=(12,3*len(flights)), constrained_layout=True)
        for ax,f in zip(np.atleast_1d(axes),flights):
            series = [r for r in rows if r["flight_id"]==f]
            t = [r["target_available_at_s"] for r in series]
            for key, label, color, style in [("truth_consumption_ah","Observed simulated consumption","#202824","-"),
                    ("history_10s","Previous 10s baseline","#c28348","--"),
                    (baseline,"Validation-selected non-neural baseline","#9b6673",":"),
                    (name,"Selected LSTM (3-seed mean)","#29735b","-")]:
                ax.plot(t,[r[key]*1000 for r in series],label=label,color=color,linestyle=style,linewidth=1.2,alpha=.9)
            ax.set_title(f"{f} | {protocol['metadata'][f]['temperature_c']} C | {protocol['metadata'][f]['track']}",loc="left")
            ax.set_ylabel("10s consumption (mAh)"); ax.set_xlabel("Target bin available at (source seconds)")
            ax.grid(alpha=.15); ax.legend(loc="best",fontsize=8,ncol=2)
        figure.suptitle(f"{group.upper()}: all held-out flights; raw predictions, no smoothing",fontsize=14)
        figure.savefig(root/f"{group}_curves.png",dpi=150); plt.close(figure)
    methods = ["history_10s","current_10s","mean_current_30s",baseline,name,"direct_full32"]
    methods = list(dict.fromkeys(methods))
    figure,axes=plt.subplots(1,2,figsize=(13,5),constrained_layout=True)
    for ax,group in zip(axes,("test","extra")):
        scores = [report["groups"][group]["methods"][n]["flight_macro_mape_pct"] for n in methods]
        bars=ax.barh(methods,scores,color=["#29735b" if n==name else "#a5ada6" for n in methods])
        ax.bar_label(bars,fmt="%.2f%%",padding=3,fontsize=9);ax.invert_yaxis();ax.set_xlim(0,max(scores)*1.22)
        ax.set_title(f"{group}: flight-equal MAPE");ax.set_xlabel("MAPE (%) — lower is better");ax.grid(axis="x",alpha=.15)
    figure.savefig(root/"method_comparison.png",dpi=150);plt.close(figure)
    bootstrap={group:flight_bootstrap(report["groups"][group]["methods"][name],report["groups"][group]["methods"][baseline]) for group in ("test","extra")}
    write_json(root/"flight_bootstrap.json",bootstrap)
    lines=["# AirSim 耗电 LSTM V3：固定划分训练与验证", "", "日期：2026-09-08。未修改原始 ZIP、原 V1/V2 模型或线上服务。", "",
        "## 结论", "",f"预先选定模型：`{name}`；开发集选定的非神经网络对照：`{baseline}`。",
        f"预设严格推广门槛：**{'通过' if report['promotion_eligible'] else '未全部通过'}**。这不是省级结题或真机验收结论。", "",
        "## 实验口径", "", "- 输入连续 30 个完整 1Hz 遥测桶；预测未来 10 秒耗电量（Ah）。不是当前 SOC 换算、SOH 或剩余航程。",
        "- 原始 10Hz 按秒均值；[k,k+1) 在 k+1 秒才可用；舍弃末尾不完整秒，缺秒不插补。目标是当前与十秒后平均电荷量之差。",
        "- 训练/验证/测试/补充集保持整架次隔离。排除 4 个疑似未起飞和 2 个异常终止架次，原因见 protocol.json。",
        "- 开发训练 8 架次；开发验证为原验证 3 架次 + 训练内预留 F008/F010。配置选定后仅在原 10 个训练架次重训，按开发最佳轮数中位数固定轮数。",
        "- 8 种配置 × 3 种子；种子不择优，部署候选为三模型预测算术均值。与 10 种无训练估算、3 种 Ridge 和 4 种树模型配置公平比较。",
        "- 所有标准化器只拟合相应训练架次。模型选择只看开发集每架次等权 MAPE，测试和 extra 不参与调参。",
        "- 测试架次此前已用于数据审计和旧 V2 冻结评估，因此不是全新盲测；必须另采未见 seed 做确认，不能反复针对这 7 架次调参。", "",
        "## 保留架次结果", "", "表中同时列出窗口加权与每架次等权 MAPE；百分比越低越好。", "",
        "| 方法 | test 窗口 MAPE | test 架次等权 MAPE | extra 窗口 MAPE | extra 架次等权 MAPE |", "|---|---:|---:|---:|---:|"]
    all_names=list(report["groups"]["test"]["methods"])
    for n in all_names:
        a,b=(report["groups"][g]["methods"][n] for g in ("test","extra"))
        label=n+("（预选候选）" if n==name else "")+("（预选对照）" if n==baseline else "")
        lines.append(f"| {label} | {a['mape_pct']:.3f}% | {a['flight_macro_mape_pct']:.3f}% | {b['mape_pct']:.3f}% | {b['flight_macro_mape_pct']:.3f}% |")
    lines += ["", "## 逐架次：不隐藏失败场景", "", "| 架次 | 温度 | 工况 | 窗口数 | 历史延续 MAPE | 预选对照 MAPE | 预选 LSTM MAPE | LSTM MAE |", "|---|---:|---|---:|---:|---:|---:|---:|"]
    for group in ("test","extra"):
        m=report["groups"][group]["methods"]
        for f in report["groups"][group]["flights"]:
            a=m[name]["per_flight"][f]; metadata=protocol["metadata"][f]
            lines.append(f"| {f} ({group}) | {metadata['temperature_c']}°C | {metadata['track']} | {a['n']} | {m['history_10s']['per_flight'][f]['mape_pct']:.3f}% | {m[baseline]['per_flight'][f]['mape_pct']:.3f}% | {a['mape_pct']:.3f}% | {a['mae_mah']:.3f} mAh |")
    lines += ["", "## 稳健性与预设门槛", ""]
    for group in ("test","extra"):
        g=report["gate"][group]; v=report["groups"][group]; seed=[x["flight_macro_mape_pct"] for x in v["lstm_seeds"][name]]
        lines += [f"- {group}：相对预选对照等权 MAPE 改善 {g['relative_macro_improvement_over_comparator_pct']:.2f}%；相对历史延续改善 {g['relative_macro_improvement_over_history_pct']:.2f}%；逐架次胜出 {g['flight_wins']}/{len(v['flights'])}。",
            f"  三个单模型等权 MAPE：{', '.join(f'{x:.3f}%' for x in seed)}；不能只报告最好的种子。",
            f"  40 秒间隔不重叠块：LSTM {v['methods'][name]['nonoverlap_40s']['mape_pct']:.3f}%，预选对照 {v['methods'][baseline]['nonoverlap_40s']['mape_pct']:.3f}%，n={v['methods'][name]['nonoverlap_40s']['n']}。"]
    latency=report["latency_local_cpu_fp32_three_seed_ensemble_ms"]
    lines += ["", "## 推理与可复现文件", "", f"- 本机 CPU，三模型 FP32 集成 + 特征选择/标准化，300 次 batch=1：中位 {latency['median']:.3f} ms，P99 {latency['p99']:.3f} ms。不含 HTTP/数据库/浏览器，也不代替边缘硬件验收。",
        "- 已保存全部模型、标准化器、随机种子、训练曲线、协议与数据哈希、逐窗口预测和全部对照结果。",
        "- protocol.json 在训练前冻结；selection.json 在打开测试前冻结；TEST_OPENED.json 标记测试暴露。",
        "- 原 V2 的误差报告与此处完整桶口径略有不同，不直接把旧 38.74% 和此处测试值当成同测试集提升率。", "",
        "## 解释与边界", "", f"- 最终候选输出公式：`{transform}`。直接模型从遥测窗口预测耗电，不套用历史延续输出；残差模型仅作为对照候选。所有模型均无事后线性纠正、平滑或加噪声。",
        "- 更复杂或加入温度不保证更准；消融结果需以独立测试为依据，不能把观察相关性写成低温物理机制已被证明。",
        "- 所有电池标签仍来自公式模型；训练结果最多支持这一仿真数据域。载荷/风速绑定、样本少、采集代码缺失等问题没有被训练解决。",
        "- 不论当前结果是否优于基线，下一轮必须先取得采集/电池模型源码、修正悬停问题，并补独立 seed 与因素解耦工况，再做一次固定模型确认。",
        "- 本轮不自动替换网页正在使用的 V2，不宣称容量衰减、真机极寒、航时、A* 或结题指标已经完成。", "",
        "## 方法依据", "", "标准化与模型选择只使用训练/验证组，遵循 [scikit-learn 数据泄漏说明](https://scikit-learn.org/stable/common_pitfalls.html)。", ""]
    (root/"RESULTS.md").write_text("\n".join(lines),encoding="utf-8")
    print(str(root/"RESULTS.md"))


if __name__=="__main__":
    main()
