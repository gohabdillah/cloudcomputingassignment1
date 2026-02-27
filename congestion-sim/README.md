# 🔬 Congestion Control Simulator

A discrete-time fluid congestion-control simulator comparing **DCTCP**, **Reno**, and a custom **SpaceCC** algorithm across data-center and "space data-center" scenarios.

Built for a cloud-computing assignment exploring how congestion-control assumptions break down when moving from sub-millisecond DC networks to high-RTT satellite/deep-space links.

## Quick Start

```bash
# 1. Create virtual environment and install dependencies
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Run data-center experiment (5 seeds by default)
python dc_experiment.py --seeds 5

# 3. Run space-DC experiment (3 CC variants × 5 seeds)
python space_experiment.py --seeds 5

# 4. Generate analysis plots
python analysis.py --exp all
# → results/dc_plots.png, results/space_plots.png

# 5. Interactive notebook (single-seed demo with inline plots)
jupyter notebook demo.ipynb
```

## Repository Structure

```
congestion-sim/
├── sim_core.py            ← Flow, Switch, Simulator classes (222 LOC)
├── dc_experiment.py       ← Exp 1: DCTCP vs Reno in low-RTT DC (84 LOC)
├── space_experiment.py    ← Exp 2: Reno / DCTCP / SpaceCC under high RTT (84 LOC)
├── analysis.py            ← Plot generation: CDF, boxplot, FCT (106 LOC)
├── demo.ipynb             ← Interactive notebook with dashboard
├── requirements.txt       ← numpy, matplotlib, seaborn, pandas, pyyaml, jupyter
├── configs/
│   ├── dc_config.yaml     ← DC: RTT=0.1 ms, buffer=300 pkts, λ=5/s, 100 KB shorts
│   └── space_config.yaml  ← Space: RTT=200 ms, jitter σ=50 ms, outages, λ=3/s
└── results/               ← Auto-generated CSVs and PNGs
```

**Total: 496 lines of Python** across 4 source files.

## Architecture

### Simulator Model

The simulator uses a **fluid discrete-time model** (Δt = 0.1 ms). Each timestep:
1. Activate any Poisson short flows whose arrival time has passed
2. Check for outage events (space scenario only)
3. Each flow sends `cwnd × PKT_BYTES / RTT` bytes into the switch
4. The switch drains up to `LINK_RATE × Δt` bytes (10 Gbps)
5. Flows receive ACK feedback: measured RTT, queue delay, ECN fraction, loss flag
6. Each flow updates its `cwnd` according to its CC algorithm

### Core Components

| Component | Description |
|---|---|
| **`Flow`** | Per-flow state: `cwnd`, base RTT, DCTCP α, EWMA-smoothed RTT. `on_ack()` dispatches to Reno / DCTCP / SpaceCC |
| **`Switch`** | Single FIFO queue. ECN-marks when queue > K packets. Tail-drops when buffer is full. 10 Gbps service rate |
| **`Simulator`** | Time-step loop with Poisson short-flow scheduling, outage injection, and jitter |

### Congestion Control Algorithms

| Algorithm | Decrease | Increase | Signal |
|---|---|---|---|
| **Reno** | `cwnd /= 2` on ECN or loss | `cwnd += 0.1 × cwnd` | ECN / tail-drop |
| **DCTCP** | `cwnd *= (2 − α) / 2` | `cwnd += 0.1 × cwnd` | EWMA of ECN fraction (g = 1/16) |
| **SpaceCC** | `cwnd *= 0.5` when smoothed ratio > 1.25 | `cwnd += cwnd × 0.5 × (Δt / RTT)` | EWMA-smoothed RTT ratio (0.9/0.1 weights) |

SpaceCC uses an **EWMA-smoothed RTT ratio** (`rtt_smooth / rtt_base`) as its congestion signal. The smoothing (factor 0.9) filters out jitter false-positives (σ = 50 ms on a 200 ms base RTT). The increase is scaled per-RTT so the window approximately doubles each RTT when uncongested.

## Experiments

### DC Experiment (`dc_experiment.py`)

| Parameter | Value |
|---|---|
| Long flows | 5 Reno + 5 DCTCP (shared bottleneck) |
| Short flows | 100 KB, Poisson λ = 5/s, per CC |
| RTT | 0.1 ms |
| Buffer | 300 packets, ECN threshold K = 30 |
| Duration | 5 000 ms |

**Key findings:**
- Mean queue delay = 0.031 ms, p99 = 0.13 ms, mean utilisation = 86%
- DCTCP short-flow median FCT ≈ 0.6 ms vs Reno ≈ 1.1 ms
- DCTCP p99 FCT = 1.0 ms vs Reno p99 = 1.8 ms

### Space Experiment (`space_experiment.py`)

| Parameter | Value |
|---|---|
| Long flows | 10 per CC variant (run separately) |
| Short flows | 10 KB, Poisson λ = 3/s |
| RTT | 200 ms + N(0, 50 ms) jitter |
| Outages | 10% probability/sec, 1 s duration (no ACKs) |
| Duration | 5 000 ms |
| CC variants | Reno, DCTCP, SpaceCC |

**Key findings:**

| CC | Utilisation (median) | FCT p99 (ms) |
|---|---|---|
| Reno | ~60% | 192 |
| DCTCP | ~80% | 99 |
| SpaceCC | ~45% (high variance) | 362 |

SpaceCC's high variance reflects outage sensitivity — utilisation collapses during outages and overshoots during recovery.

## Configuration

All parameters are in `configs/*.yaml` and can be overridden:

```yaml
# configs/dc_config.yaml
rtt_base_ms: 0.1
buffer_pkts: 300
ecn_thresh_pkts: 30
duration_ms: 5000.0
short_lambda: 5.0
short_size_bytes: 102400    # 100 KB
```

```yaml
# configs/space_config.yaml
rtt_base_ms: 200.0
duration_ms: 5000.0
rtt_jitter_std_ms: 50.0
outage_prob_per_sec: 0.1
outage_duration_ms: 1000.0
short_lambda: 3.0
```

## Interactive Notebook

`demo.ipynb` runs single-seed experiments with inline plots:

1. **DC queue delay time-series** — sawtooth pattern above ECN threshold
2. **Queue delay CDF** — DC (mixed) vs Space (per-CC)
3. **Utilisation boxplots** — per-second averages by CC
4. **Short-flow FCT boxplots** — DC (100 KB) and Space (10 KB)
5. **2×3 dashboard** — combined view saved to `results/demo_dashboard.png`
6. **SpaceCC monkey-patch cell** — modify the algorithm and re-run instantly

## Extending SpaceCC

Edit `_spacecc_update()` in `sim_core.py`, or use the monkey-patch cell in `demo.ipynb`:

```python
def _spacecc_update(self, rtt_ms, queue_ms, ecn_frac, loss):
    # Available state: self.cwnd, self.rtt_base_ms, self.rtt_smooth
    # Available signals: rtt_ms, queue_ms, ecn_frac, loss
    # Constraint: self.cwnd >= 2
    ...
```

Ideas for improvement:
- **Outage detection:** Track time since last ACK; freeze cwnd during outages, then probe aggressively
- **Hybrid ECN + delay:** Use ECN when available, fall back to delay-based during outage recovery
- **COPA-style targeting:** Aim for a specific queuing delay (e.g., 1/δ of base RTT)

## Output Files

```
results/
├── dc_metrics.csv      ← per-seed: mean_util, p99_queue, reno/dctcp FCT p99
├── space_metrics.csv   ← per-seed per-CC: mean_util, p99_queue, fct_p99
├── dc_plots.png        ← multi-seed DC results (3-panel)
├── space_plots.png     ← multi-seed Space results (3-panel)
└── demo_dashboard.png  ← 2×3 dashboard from notebook
```

## References

- M. Alizadeh et al., "Data Center TCP (DCTCP)", SIGCOMM 2010
- V. Jacobson, "Congestion Avoidance and Control", SIGCOMM 1988
- K. Ramakrishnan et al., "The Addition of ECN to IP", RFC 3168, 2001
- L. Brakmo & L. Peterson, "TCP Vegas", IEEE JSAC, 1995
- K. Winstein & H. Balakrishnan, "TCP ex Machina", SIGCOMM 2013

## License

MIT — for educational use.
