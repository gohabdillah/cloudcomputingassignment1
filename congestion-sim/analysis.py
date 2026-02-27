#!/usr/bin/env python3
"""analysis.py – Generate plots from experiment CSV results."""
import argparse, os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

OUT_DIR = "results"
sns.set_theme(style="whitegrid", font_scale=1.1)

def _save(fig, name: str):
    path = os.path.join(OUT_DIR, name)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  → saved {path}")

def plot_dc(csv_path: str):
    df = pd.read_csv(csv_path)
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))

    # 1 – Queue delay CDF (per-seed p99 values)
    ax = axes[0]
    vals = df["p99_queue_delay_ms"].dropna().sort_values().values
    cdf = np.arange(1, len(vals) + 1) / len(vals)
    ax.step(vals, cdf, linewidth=2)
    ax.set_xlabel("p99 Queue Delay (ms)")
    ax.set_ylabel("CDF")
    ax.set_title("DC: Queue Delay p99 CDF")

    # 2 – Utilisation box plot
    ax = axes[1]
    sns.boxplot(y=df["mean_util"], ax=ax, color="steelblue")
    ax.set_ylabel("Mean Link Utilisation"); ax.set_title("DC: Utilisation"); ax.set_ylim(0, 1.05)
    # 3 – FCT p99: Reno vs DCTCP
    ax = axes[2]
    fct_data = []
    for _, row in df.iterrows():
        if row["reno_fct_p99_ms"] is not None and not np.isnan(row["reno_fct_p99_ms"]):
            fct_data.append({"CC": "Reno", "FCT p99 (ms)": row["reno_fct_p99_ms"]})
        if row["dctcp_fct_p99_ms"] is not None and not np.isnan(row["dctcp_fct_p99_ms"]):
            fct_data.append({"CC": "DCTCP", "FCT p99 (ms)": row["dctcp_fct_p99_ms"]})
    if fct_data:
        fct_df = pd.DataFrame(fct_data)
        sns.boxplot(x="CC", y="FCT p99 (ms)", hue="CC", data=fct_df, ax=ax,
                    palette={"Reno": "salmon", "DCTCP": "steelblue"}, legend=False)
    ax.set_title("DC: Short-Flow FCT p99")

    fig.suptitle("Data-Center Experiment Results", fontsize=14, y=1.02)
    _save(fig, "dc_plots.png")

def plot_space(csv_path: str):
    df = pd.read_csv(csv_path)
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))

    # 1 – Queue delay CDF per CC
    ax = axes[0]
    for cc, grp in df.groupby("cc"):
        vals = grp["p99_queue_delay_ms"].dropna().sort_values().values
        cdf = np.arange(1, len(vals) + 1) / len(vals)
        ax.step(vals, cdf, label=cc, linewidth=2)
    ax.set_xlabel("p99 Queue Delay (ms)")
    ax.set_ylabel("CDF")
    ax.set_title("Space: Queue Delay p99 CDF")
    ax.legend()

    # 2 – Utilisation box plot per CC
    ax = axes[1]
    sns.boxplot(x="cc", y="mean_util", hue="cc", data=df, ax=ax, palette="Set2", legend=False)
    ax.set_ylabel("Mean Utilisation"); ax.set_title("Space: Utilisation by CC"); ax.set_ylim(0, 1.05)
    # 3 – FCT p99 per CC
    ax = axes[2]
    fct_df = df[df["fct_p99_ms"].notna()]
    if len(fct_df):
        sns.boxplot(x="cc", y="fct_p99_ms", hue="cc", data=fct_df, ax=ax, palette="Set2", legend=False)
    ax.set_ylabel("FCT p99 (ms)"); ax.set_title("Space: Short-Flow FCT p99")

    fig.suptitle("Space-DC Experiment Results", fontsize=14, y=1.02)
    _save(fig, "space_plots.png")

def main():
    parser = argparse.ArgumentParser(description="Plot congestion sim results")
    parser.add_argument("--exp", choices=["dc", "space", "all"], default="all",
                        help="Which experiment to plot")
    args = parser.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)

    if args.exp in ("dc", "all"):
        p = os.path.join(OUT_DIR, "dc_metrics.csv")
        if os.path.exists(p):
            plot_dc(p)
        else:
            print(f"⚠ {p} not found – run dc_experiment.py first")

    if args.exp in ("space", "all"):
        p = os.path.join(OUT_DIR, "space_metrics.csv")
        if os.path.exists(p):
            plot_space(p)
        else:
            print(f"⚠ {p} not found – run space_experiment.py first")

if __name__ == "__main__":
    main()
