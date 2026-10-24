"""Command line interface.

  python -m agentid_tracker snapshot [--venues flap,four,gang] [--all] [--json]
  python -m agentid_tracker watch    [--interval 15] [--iterations N] [--fast-pp 10] [--json] [--alert-baseline]
  python -m agentid_tracker creator  <address>
  python -m agentid_tracker rpc-check
"""
import argparse
import json
import sys
import time

from . import __version__, reputation
from . import rpc as R
from .alerts import Alerter
from .tracker import Tracker


def _venues(s):
    v = tuple(x.strip() for x in s.split(",") if x.strip())
    bad = [x for x in v if x not in ("flap", "four", "gang")]
    if bad:
        sys.exit(f"unknown venue(s): {bad}; choose from flap,four,gang")
    return v


def bar(pct, width=20):
    n = int(round(min(100.0, max(0.0, pct)) / 100 * width))
    return "#" * n + "." * (width - n)


def cmd_snapshot(a):
    t = Tracker(venues=_venues(a.venues), four_lookback=a.four_lookback)
    rows, _ = t.step()
    db = reputation.build(rows)
    for r in rows:
        if r.get("creator"):
            rep = reputation.score(r["creator"], db, current=r)
            r["creator_score"] = rep["score"]
            r["creator_reasons"] = rep["reasons"]
    if a.json:
        print(json.dumps({"ts": int(time.time()), "rows": rows, "errors": t.errors}, ensure_ascii=False, default=str, indent=1))
        return
    for venue in t.venues:
        name = {"flap": "flap_agent_curve", "four": "four_agent", "gang": "gang"}[venue]
        vr = [r for r in rows if r["venue"] == name]
        live = [r for r in vr if not r.get("launched")]
        print(f"\n== {name}: {len(vr)} launches seen, {len(live)} still on the curve, "
              f"{len(vr) - len(live)} launched/graduated ==")
        if venue in t.errors:
            print(f"   ERROR: {t.errors[venue]}")
        show = vr if a.all else live
        show = sorted(show, key=lambda r: -(r.get("fill_pct") or 0))[: a.top]
        for r in show:
            cs = r.get("creator_score")
            extra = f" buyers={r['unique_buyers']}" if "unique_buyers" in r else ""
            extra += " [TEST]" if r.get("test_token") else ""
            extra += " [launched]" if r.get("launched") else ""
            print(f"  {(r.get('symbol') or '?')[:14]:<14} {bar(r.get('fill_pct') or 0)} {r.get('fill_pct', 0):6.2f}% "
                  f"{r.get('raised')}/{r.get('cap')} {r.get('quote'):<5} creator_score={cs if cs is not None else 'n/a':>3}"
                  f"{extra}  {r['link']}" + ("" if r["id"].lower() in r["link"].lower() else f" market={r['id']}"))
        if not show:
            print("  (nothing live right now)" if not a.all else "  (none)")


def cmd_watch(a):
    al = Alerter(webhook=a.webhook, json_lines=a.json)
    t = Tracker(venues=_venues(a.venues), fast_pp=a.fast_pp, fast_window=a.fast_window, four_lookback=a.four_lookback,
                alerter=al, alert_baseline=a.alert_baseline)
    print(f"agentid-launch-tracker {__version__}: watching {','.join(t.venues)} every {a.interval}s "
          f"(RPC: {', '.join(R.host(u) for u in R.endpoints())}; read-only)", flush=True)
    i = 0
    try:
        while a.iterations is None or i < a.iterations:
            t0 = time.time()
            rows, events = t.step()
            i += 1
            live = sum(1 for r in rows if not r.get("launched"))
            err = f" errors={t.errors}" if t.errors else ""
            print(f"  poll #{i}: {len(rows)} launches tracked, {live} live, {len(events)} alerts{err}", flush=True)
            t.errors.clear()
            if a.iterations is not None and i >= a.iterations:
                break
            time.sleep(max(1.0, a.interval - (time.time() - t0)))
    except KeyboardInterrupt:
        print("stopped")


def cmd_creator(a):
    t = Tracker(venues=_venues(a.venues), four_lookback=a.four_lookback)
    rows, _ = t.step()
    db = reputation.build(rows)
    rep = reputation.score(a.address, db)
    rep["launches"] = [{k: r.get(k) for k in ("venue", "symbol", "fill_pct", "launched", "link")}
                       for r in db.get(a.address.lower(), [])]
    print(json.dumps(rep, ensure_ascii=False, indent=1, default=str))


def cmd_rpc_check(a):
    print("endpoints:", [R.host(u) for u in R.endpoints()])
    print("head block:", R.block_number())


def main(argv=None):
    p = argparse.ArgumentParser(prog="agentid_tracker", description="Read-only tracker for Agent-ID-gated launches on BNB Chain")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--venues", default="flap,four,gang", help="comma list of flap,four,gang")
        sp.add_argument("--four-lookback", type=int, default=5000, help="blocks of Four history to scan at start (~0.45 s/block; public nodes allow up to ~9000)")

    s = sub.add_parser("snapshot", help="one-shot table of current launches"); common(s)
    s.add_argument("--all", action="store_true", help="include launched/graduated markets")
    s.add_argument("--top", type=int, default=15)
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_snapshot)

    w = sub.add_parser("watch", help="poll and alert on new launches / fast fills / near-full / launched"); common(w)
    w.add_argument("--interval", type=float, default=15.0)
    w.add_argument("--iterations", type=int, default=None, help="stop after N polls (default: run forever)")
    w.add_argument("--fast-pp", type=float, default=10.0, help="alert when fill rises this many points within --fast-window")
    w.add_argument("--fast-window", type=int, default=120, help="seconds")
    w.add_argument("--webhook", default=None, help="webhook URL (default: env ALERT_WEBHOOK_URL)")
    w.add_argument("--json", action="store_true", help="print alerts as JSON lines")
    w.add_argument("--alert-baseline", action="store_true", help="also alert for live markets found on the first poll")
    w.set_defaults(fn=cmd_watch)

    c = sub.add_parser("creator", help="reputation of one creator address"); common(c)
    c.add_argument("address")
    c.set_defaults(fn=cmd_creator)

    r = sub.add_parser("rpc-check", help="show configured endpoints and head block")
    r.set_defaults(fn=cmd_rpc_check)

    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
