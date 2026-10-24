"""Simple, transparent creator reputation from launches the tracker can see (all venues).

It is a tie-breaker / warning light, NOT a recommendation. Most creators are new and score 0.
  +1 per earlier launch by the same creator that reached launch/graduation (max +2)
  +1 at least 2 earlier launches and >= 50% of them launched
  -1 "dead launcher": >= 3 earlier launches, none launched, none ever >= 30% filled
  -2 "spam launcher": >= 5 launches by the same creator in the data set
"""
from collections import defaultdict


def _order_key(r):
    # flap: market index, four: block, gang: created_at -> comparable "earlier than" within a venue
    return (r.get("index") if r.get("index") is not None else r.get("block") or r.get("created_at") or 0)


def build(rows):
    by = defaultdict(list)
    for r in rows:
        c = (r.get("creator") or "").lower()
        if c:
            by[c].append(r)
    return by


def score(creator, rows_by_creator, current=None):
    hist = list(rows_by_creator.get((creator or "").lower(), []))
    if current is not None:
        hist = [h for h in hist if h["id"] != current["id"] and
                (h["venue"] != current["venue"] or _order_key(h) < _order_key(current))]
    n = len(hist)
    launched = sum(1 for h in hist if h.get("launched"))
    s, reasons = 0, []
    if launched:
        s += min(2, launched); reasons.append(f"+{min(2, launched)} earlier launches that graduated: {launched}")
    if n >= 2 and launched / n >= 0.5:
        s += 1; reasons.append(f"+1 graduation rate {launched}/{n}")
    if n >= 3 and launched == 0 and all((h.get("fill_pct") or 0) < 30 for h in hist):
        s -= 1; reasons.append(f"-1 dead launcher ({n} launches, none >= 30%)")
    total = len(rows_by_creator.get((creator or "").lower(), []))
    if total >= 5:
        s -= 2; reasons.append(f"-2 spam launcher ({total} launches seen)")
    if not n:
        reasons.append("0 no earlier launches seen")
    return {"creator": creator, "score": s, "earlier_launches": n, "graduated": launched, "reasons": reasons,
            "venues": sorted({h["venue"] for h in hist})}
