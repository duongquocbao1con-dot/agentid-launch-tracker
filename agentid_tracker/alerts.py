"""Alert sinks: stdout (always) and an optional webhook (ALERT_WEBHOOK_URL).

The webhook receives a JSON POST: {"content": "<one-line text>", "event": {...}}.
"content" makes it work out-of-the-box with Discord webhooks; other services can read "event".
"""
import json
import os
import time
import urllib.request

UA = "agentid-launch-tracker/0.1"


def fmt(ev):
    t = time.strftime("%H:%M:%S", time.localtime(ev["ts"]))
    rep = ev.get("creator_score")
    rep_s = f" creator_score={rep:+d}" if isinstance(rep, int) else ""
    delta = f" (+{ev['delta_pp']:.1f}pp)" if ev.get("delta_pp") else ""
    return (f"[{t}] {ev['event'].upper():<11} {ev['venue']:<16} {ev.get('symbol') or '?':<12} "
            f"fill={ev.get('fill_pct', 0):6.2f}%{delta} raised={ev.get('raised')}/{ev.get('cap')} {ev.get('quote')}"
            f"{rep_s} {ev.get('link')}")


class Alerter:
    def __init__(self, webhook=None, json_lines=False):
        self.webhook = webhook if webhook is not None else os.environ.get("ALERT_WEBHOOK_URL", "").strip() or None
        self.json_lines = json_lines

    def send(self, ev):
        print(json.dumps(ev, ensure_ascii=False, default=str) if self.json_lines else fmt(ev), flush=True)
        if self.webhook:
            body = json.dumps({"content": fmt(ev)[:1900], "event": ev}, ensure_ascii=False, default=str).encode()
            req = urllib.request.Request(self.webhook, data=body,
                                         headers={"Content-Type": "application/json", "User-Agent": UA})
            try:
                urllib.request.urlopen(req, timeout=10).read()
            except Exception as e:
                print(f"  (webhook failed: {type(e).__name__})", flush=True)
