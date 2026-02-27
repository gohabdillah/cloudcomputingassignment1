# 🔬 Congestion Control Simulator

A toy discrete-time congestion-control simulator for comparing **DCTCP** and **Reno** in data-center and "space datacenter" scenarios.

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run data-center experiment (20 seeds, ~30 s)
python dc_experiment.py

# 3. Run space-DC experiment (3 CC variants × 20 seeds, ~2 min)
python space_experiment.py

# 4. Generate plots
python analysis.py --exp all
# → results/dc_plots.png, results/space_plots.png
```

## Repo Structure

```
congestion-sim/
├── README.md                 ← you are here
├── requirements.txt          ← numpy, matplotlib, seaborn, pandas, pyyaml
├── sim_core.py               ← Flow, Switch, Simulator classes
├── dc_experiment.py          ← Exp 1: DCTCP vs Reno (low RTT)
├── space_experiment.py       ← Exp 2: high RTT + outages
├── analysis.py               ← plotting (CDF, boxplot, FCT)
├── demo.ipynb                ← single-run interactive notebook
├── configs/
│   ├── dc_config.yaml        ← DC parameters (RTT=0.1ms, buf=300)
│   └── space_config.yaml     ← Space parameters (RTT=200ms, jitter, outages)
└── results/                  ← auto-generated CSVs and PNGs
```

## Architecture

| Component | Description |
|---|---|
| **`Flow`** | Per-flow state: `cwnd`, RTT, `alpha` (DCTCP EWMA). `on_ack()` dispatches to Reno / DCTCP / SpaceCC logic |
| **`Switch`** | Single FIFO queue (bytes). ECN marks when queue > K packets. Tail-drops when buffer full. 10 Gbps service rate |
| **`Simulator`** | Discrete time-step loop (default Δt = 0.1 ms). Enqueues flow traffic, drains the switch, feeds back ACKs with RTT + queue delay |

### Congestion Control Variants

- **Reno:** Halve `cwnd` on ECN/loss; increase by 10% per RTT otherwise
- **DCTCP:** EWMA of ECN fraction → `cwnd *= (2 − α) / 2`; much gentler reduction
- **SpaceCC (stub):** Falls back to Reno — **fill in `Flow._spacecc_update()`** with your own algorithm

## Experiments

### DC Experiment (`dc_experiment.py`)
- 5 Reno + 5 DCTCP long flows
- Poisson short flows (10 KB, λ = 1/sec)
- RTT = 0.1 ms, buffer = 300 packets
- **Expected:** DCTCP has significantly lower queue delay than Reno

### Space Experiment (`space_experiment.py`)
- 10 long flows (single CC per run)
- RTT = 200 ms + N(0, 50 ms) jitter
- 10% outage probability (1 s duration, no ACKs)
- Tests all 3 CC variants separately

## Configuration

Edit YAML files in `configs/` to change parameters:

```yaml
# configs/dc_config.yaml
rtt_base_ms: 0.1
buffer_pkts: 300
ecn_thresh_pkts: 30
duration_ms: 1000.0
```

## Extending: Implement SpaceCC

Open `sim_core.py` and find the `_spacecc_update` method:

```python
def _spacecc_update(self, rtt_ms, queue_ms, ecn_frac, loss):
    # TODO: Your delay-based algorithm here
    # Available signals: rtt_ms, queue_ms, ecn_frac, loss
    # Must set self.cwnd (>= 2)
    pass
```

Ideas: BBR-like pacing, COPA-style delay targeting, or hybrid ECN + delay.

## Output

After running both experiments + analysis:

```
results/
├── dc_metrics.csv
├── space_metrics.csv
├── dc_plots.png       ← queue CDF, utilisation, FCT comparison
└── space_plots.png    ← same, per-CC variant
```

## License

MIT – for educational use.
