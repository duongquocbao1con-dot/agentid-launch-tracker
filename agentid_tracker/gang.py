"""GANG.fun - agent-only launchpad on BNB Chain (20 BNB to graduate). Read-only, public JSON API."""
import json
import time
import urllib.request

API = "https://gang.fun/api/tokens"
UA = "agentid-launch-tracker/0.1 (+read-only)"


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def snapshot(max_items=300):
    items, off = [], 0
    while off < max_items:
        page = _get(f"{API}?limit=50&offset={off}").get("items", [])
        items += page
        if len(page) < 50:
            break
        off += 50
        time.sleep(0.5)
    out = []
    for x in items:
        out.append({
            "venue": "gang", "id": x["address"].lower(), "name": x.get("name"), "symbol": x.get("symbol"), "quote": "BNB",
            "fill_pct": round(float(x.get("progressPct") or 0), 2), "raised": round(float(x.get("raisedBnb") or 0), 4),
            "cap": 20.0, "buys": None, "sells": None, "trades": x.get("trades"), "holders": x.get("holders"),
            "creator": (x.get("creator") or "").lower() or None, "creator_handle": x.get("creatorHandle"),
            "created_at": x.get("createdAt"), "launched": bool(x.get("graduated")),
            "link": f"https://gang.fun/token/{x['address'].lower()}",
        })
    return out
