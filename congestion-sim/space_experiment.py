#!/usr/bin/env python3
"""space_experiment.py – Space datacenter congestion experiment."""
import argparse, csv, os, yaml
import numpy as np
from sim_core import Flow, Switch, Simulator

DEFAULT_CFG = "configs/space_config.yaml"
OUT_DIR = "results"


def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def run_single(cfg: dict, cc: str, seed: int):
    """Run one trial for a single CC variant."""
    rng = np.random.default_rng(seed)
    sw = Switch(buffer_pkts=cfg["buffer_pkts"], ecn_thresh_pkts=cfg["ecn_thresh_pkts"])
    sim = Simulator(dt_ms=cfg["dt_ms"], duration_ms=cfg["duration_ms"],
                    switch=sw, rng=rng)

    # outage parameters
    sim.outage_prob = cfg.get("outage_prob_per_sec", 0.1)
    sim.outage_duration_ms = cfg.get("outage_duration_ms", 1000.0)
    sim.rtt_jitter_std_ms = cfg.get("rtt_jitter_std_ms", 50.0)

    # long flows (all same cc)
    for fid in range(cfg["num_long_flows"]):
        sim.add_flow(Flow(fid, cc, rtt_base_ms=cfg["rtt_base_ms"]))

    # Poisson short flows
    sim.schedule_short_flows(
        lam_per_sec=cfg["short_lambda"],
        size_bytes=cfg["short_size_bytes"],
        cc=cc,
        rtt_base_ms=cfg["rtt_base_ms"],
    )

    metrics, fcts = sim.run()
    return metrics, fcts


def summarise(metrics, fcts, cc: str, seed: int):
    delays = [m.queue_delay_ms for m in metrics]
    utils = [m.util for m in metrics]
    fct_vals = [f.fct_ms for f in fcts]
    return {
        "cc": cc,
        "seed": seed,
        "mean_queue_delay_ms": float(np.mean(delays)),
        "p99_queue_delay_ms": float(np.percentile(delays, 99)),
        "mean_util": float(np.mean(utils)),
        "fct_p99_ms": float(np.percentile(fct_vals, 99)) if fct_vals else None,
        "num_short_flows": len(fcts),
    }


def main():
    parser = argparse.ArgumentParser(description="Space-DC congestion experiment")
    parser.add_argument("--config", default=DEFAULT_CFG)
    parser.add_argument("--seeds", type=int, default=20)
    args = parser.parse_args()

    cfg = load_config(args.config)
    os.makedirs(OUT_DIR, exist_ok=True)

    rows = []
    for cc in ("reno", "dctcp", "spacecc"):
        for s in range(args.seeds):
            print(f"  Space [{cc}] seed {s+1}/{args.seeds} …", flush=True)
            metrics, fcts = run_single(cfg, cc, seed=s)
            rows.append(summarise(metrics, fcts, cc, s))

    out_path = os.path.join(OUT_DIR, "space_metrics.csv")
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    print(f"✓ Saved {out_path}  ({len(rows)} runs)")


if __name__ == "__main__":
    main()
