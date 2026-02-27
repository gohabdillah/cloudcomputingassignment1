#!/usr/bin/env python3
"""dc_experiment.py – Data-center congestion experiment."""
import argparse, csv, os, yaml
import numpy as np
from sim_core import Flow, Switch, Simulator

DEFAULT_CFG = "configs/dc_config.yaml"
OUT_DIR = "results"


def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def run_single(cfg: dict, seed: int):
    """Run one trial; return (metrics_list, fct_list)."""
    rng = np.random.default_rng(seed)
    sw = Switch(buffer_pkts=cfg["buffer_pkts"], ecn_thresh_pkts=cfg["ecn_thresh_pkts"])
    sim = Simulator(dt_ms=cfg["dt_ms"], duration_ms=cfg["duration_ms"],
                    switch=sw, rng=rng)

    # long flows
    fid = 0
    for cc in ("reno", "dctcp"):
        for _ in range(cfg["long_flows_per_cc"]):
            sim.add_flow(Flow(fid, cc, rtt_base_ms=cfg["rtt_base_ms"]))
            fid += 1

    # Poisson short flows (alternate cc)
    for cc in ("reno", "dctcp"):
        sim.schedule_short_flows(
            lam_per_sec=cfg["short_lambda"],
            size_bytes=cfg["short_size_bytes"],
            cc=cc,
            rtt_base_ms=cfg["rtt_base_ms"],
        )

    metrics, fcts = sim.run()
    return metrics, fcts


def summarise(metrics, fcts, seed: int):
    """Return a dict row for the CSV."""
    delays = [m.queue_delay_ms for m in metrics]
    utils = [m.util for m in metrics]
    reno_fcts = [f.fct_ms for f in fcts if f.cc == "reno"]
    dctcp_fcts = [f.fct_ms for f in fcts if f.cc == "dctcp"]
    return {
        "seed": seed,
        "mean_queue_delay_ms": float(np.mean(delays)),
        "p99_queue_delay_ms": float(np.percentile(delays, 99)),
        "mean_util": float(np.mean(utils)),
        "reno_fct_p99_ms": float(np.percentile(reno_fcts, 99)) if reno_fcts else None,
        "dctcp_fct_p99_ms": float(np.percentile(dctcp_fcts, 99)) if dctcp_fcts else None,
        "num_short_flows": len(fcts),
    }


def main():
    parser = argparse.ArgumentParser(description="DC congestion experiment")
    parser.add_argument("--config", default=DEFAULT_CFG)
    parser.add_argument("--seeds", type=int, default=20)
    args = parser.parse_args()

    cfg = load_config(args.config)
    os.makedirs(OUT_DIR, exist_ok=True)

    rows = []
    for s in range(args.seeds):
        print(f"  DC seed {s+1}/{args.seeds} …", flush=True)
        metrics, fcts = run_single(cfg, seed=s)
        rows.append(summarise(metrics, fcts, s))

    out_path = os.path.join(OUT_DIR, "dc_metrics.csv")
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    print(f"✓ Saved {out_path}  ({len(rows)} runs)")


if __name__ == "__main__":
    main()
