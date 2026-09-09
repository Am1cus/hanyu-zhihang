"""Scientific plots of frozen exploratory outputs; no smoothing or fitting."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment",type=Path,default=Path(__file__).parent/"experiments/capacity_v3_20260908")
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    report=json.loads((args.experiment/"evaluation.json").read_text())
    rows=json.loads((args.experiment/"heldout_predictions.json").read_text())
    protocol=json.loads((args.experiment/"protocol.json").read_text())
    name="residual_core32"
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":10,"axes.spines.top":False,
                         "axes.spines.right":False,"figure.facecolor":"#faf9f5","axes.facecolor":"#faf9f5"})
    methods=[("history_10s","Previous 10s"),("mean_current_20s","20s current mean"),
             ("tree_residual_l7_i120","Tree (7 leaves)"),("tree_residual_l15_i120","Tree (15 leaves)"),
             ("direct_full32","Original preselected LSTM"),(name,"Frozen residual LSTM")]
    figure,axes=plt.subplots(1,2,figsize=(12,4.8),constrained_layout=True)
    for ax,group in zip(axes,("test","extra")):
        scores=[report["groups"][group]["methods"][key]["mape_pct"] for key,_ in methods]
        bars=ax.barh([label for _,label in methods],scores,
                     color=["#347653" if key==name else "#a9b0a8" for key,_ in methods])
        ax.bar_label(bars,fmt="%.2f%%",padding=4)
        ax.invert_yaxis();ax.set_xlim(0,6.5);ax.grid(axis="x",alpha=.16)
        ax.set_title("3 retained test flights" if group=="test" else "4 supplementary flights")
        ax.set_xlabel("Next-10s consumption MAPE (%) — lower is better")
    figure.suptitle("Residual LSTM candidate — exploratory model selection, fresh confirmation pending",fontsize=12)
    figure.savefig(args.output/"method_comparison.png",dpi=160);plt.close(figure)
    for group in ("test","extra"):
        flights=report["groups"][group]["flights"]
        figure,axes=plt.subplots(len(flights),1,figsize=(12,3*len(flights)),constrained_layout=True)
        for ax,flight in zip(np.atleast_1d(axes),flights):
            series=[r for r in rows if r["flight_id"]==flight]
            time=[r["target_available_at_s"] for r in series]
            for key,label,color,style in [("truth_consumption_ah","Simulated ground truth","#202824","-"),
                    ("history_10s","Previous 10s baseline","#c08449","--"),
                    ("tree_residual_l7_i120","Preselected tree comparator","#a07883",":"),
                    (name,"Frozen residual LSTM","#347653","-")]:
                ax.plot(time,[r[key]*1000 for r in series],label=label,color=color,linestyle=style,linewidth=1.2)
            meta=protocol["metadata"][flight]
            ax.set_title(f"{flight} | {meta['temperature_c']} C | {meta['track']}",loc="left")
            ax.set_xlabel("Target bin availability (source seconds)");ax.set_ylabel("10s consumption (mAh)")
            ax.legend(fontsize=8,ncol=2);ax.grid(alpha=.15)
        figure.suptitle("All retained flights | raw outputs, no smoothing | candidate requires new confirmation",fontsize=12)
        figure.savefig(args.output/f"{group}_curves.png",dpi=150);plt.close(figure)
    print(str(args.output.resolve()))


if __name__=="__main__":main()
