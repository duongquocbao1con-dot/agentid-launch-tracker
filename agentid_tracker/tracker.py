"""Polling loop: snapshot every venue, diff against the previous snapshot, emit alerts."""
import time

from . import flap_curve, gang, reputation
from .four_agent import FourAgentScanner

NEAR_FULL = (80.0, 95.0)


class Tracker:
    def __init__(self, venues=("flap", "four", "gang"), fast_pp=10.0, fast_window=120, four_lookback=5000,
                 alerter=None, alert_baseline=False):
        self.venues = venues
        self.fast_pp, self.fast_window = fast_pp, fast_window
        self.four = FourAgentScanner(four_lookback) if "four" in venues else None
        self.prev = {}        # (venue,id) -> row
        self.hist = {}        # (venue,id) -> [(ts, fill)]
        self.fired = {}       # (venue,id,event) -> fill when fired
        self.alerter = alerter
        self.alert_baseline = alert_baseline
        self.baseline_done = False
        self.errors = {}

    def collect(self):
        rows = []
        if "flap" in self.venues:
            try:
                rows += flap_curve.snapshot(with_creators=True)
            except Exception as e:
                self.errors["flap"] = f"{type(e).__name__}: {e}"[:200]
        if self.four is not None:
            try:
                self.four.update(); rows += self.four.rows()
            except Exception as e:
                self.errors["four"] = f"{type(e).__name__}: {e}"[:200]
        if "gang" in self.venues:
            try:
                rows += gang.snapshot()
            except Exception as e:
                self.errors["gang"] = f"{type(e).__name__}: {e}"[:200]
        return rows

    def _emit(self, event, r, rep_db, **extra):
        rep = reputation.score(r.get("creator"), rep_db, current=r) if r.get("creator") else None
        ev = {"ts": int(time.time()), "event": event, "venue": r["venue"], "id": r["id"], "name": r.get("name"),
              "symbol": r.get("symbol"), "quote": r.get("quote"), "fill_pct": r.get("fill_pct"), "raised": r.get("raised"),
              "cap": r.get("cap"), "creator": r.get("creator"), "link": r.get("link"),
              "creator_score": rep["score"] if rep else None, "creator_reasons": rep["reasons"] if rep else None}
        ev.update(extra)
        if self.alerter:
            self.alerter.send(ev)
        return ev

    def step(self):
        rows = self.collect()
        rep_db = reputation.build(rows)
        now = time.time()
        events = []
        for r in rows:
            k = (r["venue"], r["id"])
            p = self.prev.get(k)
            h = self.hist.setdefault(k, [])
            h.append((now, r.get("fill_pct") or 0.0))
            while h and h[0][0] < now - max(self.fast_window, 600):
                h.pop(0)
            if p is None:
                if self.baseline_done or (self.alert_baseline and not r.get("launched")):
                    events.append(self._emit("new_launch", r, rep_db))
                continue
            if r.get("launched") and not p.get("launched"):
                events.append(self._emit("launched", r, rep_db))
                continue
            if r.get("launched"):
                continue
            fill = r.get("fill_pct") or 0.0
            win = [f for t, f in h if t >= now - self.fast_window]
            delta = fill - min(win) if len(win) >= 2 else 0.0
            last = self.fired.get(k + ("fast_fill",))
            if delta >= self.fast_pp and (last is None or fill >= last + self.fast_pp):
                events.append(self._emit("fast_fill", r, rep_db, delta_pp=round(delta, 2)))
                self.fired[k + ("fast_fill",)] = fill
            for thr in NEAR_FULL:
                if fill >= thr > (p.get("fill_pct") or 0.0):
                    events.append(self._emit("near_full", r, rep_db, threshold=thr))
        self.prev = {(r["venue"], r["id"]): r for r in rows}
        self.baseline_done = True
        return rows, events

    def run(self, interval=15.0, iterations=None):
        i = 0
        while iterations is None or i < iterations:
            t0 = time.time()
            self.step()
            i += 1
            if iterations is not None and i >= iterations:
                break
            time.sleep(max(1.0, interval - (time.time() - t0)))
