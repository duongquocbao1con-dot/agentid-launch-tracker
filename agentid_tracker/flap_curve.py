"""flap.sh "ID Agent Curve" (mini app https://flap.sh/apps/agent-bonding-curve) - read-only.

How it works (see docs/TUTORIAL.md): anyone can open a pre-launch market; only wallets holding a
Binance "Agent ID" (.ai) NFT can buy curve shares. When the pool reaches its cap (5 BNB for BNB
markets) the real token is deployed on flap and holders claim 1:1.

On-chain contracts (BNB Chain), taken from the app's public manifest:
  Factory  marketCount() / markets(i)                      -> every market address
  Reader   marketCards(address[<=5]) / marketDetail(addr)  -> name, symbol, phase, pool, cap, progress, creator
"""
import time

from eth_abi import decode, encode
from eth_utils import to_checksum_address

from . import rpc as R

FACTORY = "0xC55820f24015bE7c4f18949D9e1363A3609B300e"
READER = "0x18Aa6C93f1887a243fdc348C9A77F5136555174a"
AGENT_ID_NFT = "0x60B9262456dE011F7d15a54CdD8c48bAaa8B022F"  # "SPACE ID Agent ID" (.ai) - the buy gate
ZERO = "0x" + "0" * 40
QUOTES = {
    ZERO: "BNB",
    "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c": "WBNB",
    "0x4902c5ebc598265ed2212b559b042de8a5eeec3f": "BNCB",
    "0x02fca66c1d1afb4e2a7884261eb00f63598a7436": "NVDAB",
    "0x205812cdbed920aff76c6580abd681a46d11efc7": "QQQB",
    "0xbe9d156892e55e7154bcd3cb0fea677f9d3103e1": "SPCXB",
    "0x0c6302401aa5325c2e36f170f52c00b1d220b405": "GANG",
}
PHASES = {1: "curve", 3: "launched"}
CARD_T = "(address,address,string,string,string,address,address,address,uint8,uint256,uint256,uint256,uint256,uint256,uint256,uint256)[]"
CARD_N = ["market", "quoteToken", "name", "symbol", "meta", "predictedToken", "token", "pair", "phase",
          "poolRaw", "capRaw", "progressBps", "buyCount", "sellCount", "curveH", "curveK"]
SEL_COUNT = R.selector("marketCount()")
SEL_MARKETS = R.selector("markets(uint256)")
SEL_CARDS = R.selector("marketCards(address[])")
SEL_DETAIL = R.selector("marketDetail(address)")


def quote_name(addr):
    a = (addr or ZERO).lower()
    return QUOTES.get(a, a[:10])


def market_addresses(start=0):
    (ok, raw), = R.multicall([(FACTORY, SEL_COUNT)])
    if not ok:
        raise R.RPCError("marketCount() failed")
    n = decode(["uint256"], raw)[0]
    out = []
    idx = list(range(start, n))
    for i in range(0, len(idx), 50):
        res = R.multicall([(FACTORY, SEL_MARKETS + encode(["uint256"], [j])) for j in idx[i:i + 50]])
        for ok2, raw2 in res:
            if not ok2:
                raise R.RPCError("markets(i) failed")
            out.append(to_checksum_address(decode(["address"], raw2)[0]))
    return out


def creators(markets):
    """market -> creator address (word 1 of Reader.marketDetail)."""
    out = {}
    for i in range(0, len(markets), 40):
        chunk = markets[i:i + 40]
        res = R.multicall([(READER, SEL_DETAIL + encode(["address"], [m])) for m in chunk])
        for m, (ok, raw) in zip(chunk, res):
            if ok and len(raw) >= 64:
                out[m] = to_checksum_address("0x" + raw[44:64].hex())
    return out


def cards(markets):
    """Read marketCards for many markets (5 per Reader call, 20 Reader calls per multicall)."""
    chunks = [markets[i:i + 5] for i in range(0, len(markets), 5)]
    calls = [(READER, SEL_CARDS + encode(["address[]"], [c])) for c in chunks]
    rows = []
    for i in range(0, len(calls), 20):
        for ok, raw in R.multicall(calls[i:i + 20]):
            if ok:
                rows += decode([CARD_T], raw)[0]
    out = []
    now = int(time.time())
    for c in rows:
        d = dict(zip(CARD_N, c))
        token = to_checksum_address(d["token"]) if d["token"] != ZERO else None
        out.append({
            "venue": "flap_agent_curve",
            "id": to_checksum_address(d["market"]),
            "name": d["name"],
            "symbol": d["symbol"],
            "quote": quote_name(d["quoteToken"]),
            "phase": PHASES.get(d["phase"], str(d["phase"])),
            "fill_pct": round(d["progressBps"] / 100, 2),
            "raised": round(d["poolRaw"] / 1e18, 4),
            "cap": round(d["capRaw"] / 1e18, 4),
            "buys": d["buyCount"],
            "sells": d["sellCount"],
            "token": token,
            "launched": d["phase"] >= 3 or bool(token),
            "link": f"https://flap.sh/bnb/{token}" if token else "https://flap.sh/apps/agent-bonding-curve",
            "seen_at": now,
        })
    return out


def snapshot(with_creators=True):
    ms = market_addresses()
    rows = cards(ms)
    if with_creators:
        cr = creators(ms)
        for r in rows:
            r["creator"] = cr.get(r["id"])
    order = {m: i for i, m in enumerate(ms)}
    for r in rows:
        r["index"] = order.get(r["id"])
    return rows
