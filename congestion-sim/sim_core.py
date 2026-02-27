"""sim_core.py – Toy congestion-control simulator (fluid, discrete time-step)."""

import numpy as np
from dataclasses import dataclass
from typing import List, Optional

PKT_BYTES = 1500
LINK_RATE_GBPS = 10
LINK_RATE_BPS = LINK_RATE_GBPS * 1e9
LINK_RATE_BYTES_PER_MS = LINK_RATE_BPS / 8 / 1000


class Flow:
    """Base congestion-control flow (long-lived or short)."""

    def __init__(self, fid: int, cc: str, rtt_base_ms: float,
                 size_bytes: float = float('inf')):
        self.fid, self.cc = fid, cc
        self.cwnd, self.rtt_base_ms = 10.0, rtt_base_ms
        self.size_bytes, self.sent_bytes = size_bytes, 0.0
        self.alpha, self.g = 0.0, 1/16
        self.rtt_smooth = 0.0  # EWMA smoothed RTT (for SpaceCC)
        self.finished = False
        self.start_time_ms: Optional[float] = None
        self.finish_time_ms: Optional[float] = None

    def on_ack(self, rtt_ms: float, queue_ms: float, ecn_frac: float,
               loss: bool = False):
        """Update cwnd based on congestion signal."""
        if self.cc == 'reno':
            self._reno_update(ecn_frac, loss)
        elif self.cc == 'dctcp':
            self._dctcp_update(ecn_frac)
        elif self.cc == 'spacecc':
            self._spacecc_update(rtt_ms, queue_ms, ecn_frac, loss)

    def _reno_update(self, ecn_frac: float, loss: bool):
        if loss or ecn_frac > 0:
            self.cwnd = max(self.cwnd / 2, 2)
        else:
            self.cwnd += 0.1 * self.cwnd

    def _dctcp_update(self, ecn_frac: float):
        self.alpha = (1 - self.g) * self.alpha + self.g * ecn_frac
        if ecn_frac > 0:
            self.cwnd = max(self.cwnd * (2 - self.alpha) / 2, 2)
        else:
            self.cwnd += 0.1 * self.cwnd

    def _spacecc_update(self, rtt_ms, queue_ms, ecn_frac, loss):
        """Delay-based CC for high-RTT space links. Uses EWMA-smoothed RTT
        ratio as congestion signal; aggressive ramp-up scaled per-RTT."""
        if self.rtt_smooth == 0:
            self.rtt_smooth = rtt_ms
        else:
            self.rtt_smooth = 0.9 * self.rtt_smooth + 0.1 * rtt_ms
        rtt_ratio = self.rtt_smooth / max(self.rtt_base_ms, 0.01)
        if rtt_ratio > 1.25:  # smoothed RTT says queuing
            self.cwnd = max(self.cwnd * 0.5, 2)
        else:
            # Scale increase per RTT: ~double per RTT when uncongested
            self.cwnd += self.cwnd * 0.5 * (0.1 / max(rtt_ms, 0.1))


    @property
    def rate_bytes_per_ms(self):
        """Current sending rate approximation."""
        rtt = max(self.rtt_base_ms, 0.01)
        return self.cwnd * PKT_BYTES / rtt


class Switch:
    """FIFO queue with ECN marking and tail-drop."""

    def __init__(self, buffer_pkts: int = 300, ecn_thresh_pkts: int = 30):
        self.buffer_bytes = buffer_pkts * PKT_BYTES
        self.ecn_thresh_bytes = ecn_thresh_pkts * PKT_BYTES
        self.queue_bytes = 0.0
        self.total_served_bytes = 0.0
        self.ecn_marked = 0
        self.ecn_total = 0

    def enqueue(self, bytes_in: float) -> bool:
        """Try to enqueue bytes; return False (drop/loss) if full."""
        if self.queue_bytes + bytes_in > self.buffer_bytes:
            return False
        self.queue_bytes += bytes_in
        return True

    def dequeue(self, dt_ms: float) -> float:
        """Drain up to link-rate * dt bytes; return bytes served."""
        can_serve = LINK_RATE_BYTES_PER_MS * dt_ms
        served = min(self.queue_bytes, can_serve)
        self.queue_bytes -= served
        self.total_served_bytes += served
        return served

    @property
    def queue_delay_ms(self) -> float:
        return self.queue_bytes / LINK_RATE_BYTES_PER_MS if LINK_RATE_BYTES_PER_MS else 0

    @property
    def ecn_fraction(self) -> float:
        """Fraction of packets that would be ECN-marked right now."""
        return 1.0 if self.queue_bytes > self.ecn_thresh_bytes else 0.0


@dataclass
class Metrics:
    """Collected per time-step."""
    time_ms: float = 0.0
    queue_bytes: float = 0.0
    queue_delay_ms: float = 0.0
    util: float = 0.0
    served_bytes: float = 0.0

@dataclass
class FCTRecord:
    fid: int
    cc: str
    size_bytes: float
    fct_ms: float


class Simulator:
    """Discrete time-step simulator (fluid approximation)."""

    def __init__(self, dt_ms: float = 0.1, duration_ms: float = 1000.0,
                 switch: Optional[Switch] = None, rng: Optional[np.random.Generator] = None):
        self.dt_ms = dt_ms
        self.duration_ms = duration_ms
        self.switch = switch or Switch()
        self.rng = rng or np.random.default_rng()
        self.flows: List[Flow] = []
        self.metrics: List[Metrics] = []
        self.fct_records: List[FCTRecord] = []
        self.short_flow_queue: List[Flow] = []
        self._time_ms = 0.0
        self.outage_active = False
        self.outage_prob = 0.0
        self.outage_duration_ms = 0.0
        self._outage_end_ms = -1.0
        self.rtt_jitter_std_ms = 0.0

    def add_flow(self, flow: Flow):
        flow.start_time_ms = self._time_ms
        self.flows.append(flow)

    def schedule_short_flows(self, lam_per_sec: float, size_bytes: float,
                              cc: str, rtt_base_ms: float):
        """Pre-generate Poisson short flow arrivals."""
        t = 0.0
        fid = 10000
        while t < self.duration_ms:
            gap_ms = self.rng.exponential(1000.0 / lam_per_sec)
            t += gap_ms
            if t < self.duration_ms:
                f = Flow(fid, cc, rtt_base_ms, size_bytes=size_bytes)
                f.start_time_ms = t
                self.short_flow_queue.append(f)
                fid += 1
        self.short_flow_queue.sort(key=lambda f: f.start_time_ms)

    def run(self):
        steps = int(self.duration_ms / self.dt_ms)
        for _ in range(steps):
            self._step()
        return self.metrics, self.fct_records

    def _step(self):
        t = self._time_ms

        while self.short_flow_queue and self.short_flow_queue[0].start_time_ms <= t:
            f = self.short_flow_queue.pop(0)
            f.start_time_ms = t
            self.flows.append(f)

        self._check_outage(t)
        in_outage = self.outage_active
        ecn_frac = self.switch.ecn_fraction
        loss_occurred = False

        for flow in self.flows:
            if flow.finished:
                continue
            send_bytes = flow.rate_bytes_per_ms * self.dt_ms
            ok = self.switch.enqueue(send_bytes)
            if not ok:
                loss_occurred = True
            flow.sent_bytes += send_bytes if ok else 0
            if flow.size_bytes < float('inf') and flow.sent_bytes >= flow.size_bytes:
                flow.finished, flow.finish_time_ms = True, t
                self.fct_records.append(FCTRecord(flow.fid, flow.cc, flow.size_bytes, t - flow.start_time_ms))

        served = self.switch.dequeue(self.dt_ms)

        if not in_outage:
            queue_ms = self.switch.queue_delay_ms
            for flow in self.flows:
                if flow.finished:
                    continue
                jitter = self.rng.normal(0, self.rtt_jitter_std_ms) if self.rtt_jitter_std_ms > 0 else 0.0
                rtt_ms = flow.rtt_base_ms + queue_ms + max(jitter, -flow.rtt_base_ms * 0.9)
                flow.on_ack(rtt_ms, queue_ms, ecn_frac, loss=loss_occurred)

        cap = LINK_RATE_BYTES_PER_MS * self.dt_ms
        self.metrics.append(Metrics(t, self.switch.queue_bytes, self.switch.queue_delay_ms,
                                    served / cap if cap else 0, served))

        self.flows = [f for f in self.flows if not f.finished]
        self._time_ms += self.dt_ms

    def _check_outage(self, t_ms: float):
        if t_ms < self._outage_end_ms:
            self.outage_active = True
            return
        self.outage_active = False
        if self.outage_prob > 0:
            p = self.outage_prob * (self.dt_ms / 1000.0)
            if self.rng.random() < p:
                self.outage_active = True
                self._outage_end_ms = t_ms + self.outage_duration_ms
