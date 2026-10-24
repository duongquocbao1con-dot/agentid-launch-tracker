"""Minimal read-only BSC JSON-RPC client with public-endpoint fallback.

Endpoints come from the env var BSC_RPC_URLS (comma separated). Default: public endpoints
(publicnode first). No API key is needed or read. Only read methods are used:
eth_blockNumber, eth_call, eth_getLogs, eth_getBlockByNumber.
"""
import json
import os
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

from eth_abi import decode, encode
from eth_utils import keccak, to_checksum_address

DEFAULT_RPCS = [
    "https://bsc-rpc.publicnode.com",
    "https://rpc-bsc.48.club",
    "https://bsc.publicnode.com",
]
UA = "agentid-launch-tracker/0.1 (+read-only)"
MULTICALL3 = "0xcA11bde05977b3631167028862bE2a173976CA11"  # canonical Multicall3, same address on every EVM chain
READ_METHODS = {"eth_blockNumber", "eth_call", "eth_getLogs", "eth_getBlockByNumber", "eth_chainId"}


def endpoints():
    env = os.environ.get("BSC_RPC_URLS", "").strip()
    urls = [u.strip() for u in env.split(",") if u.strip()] if env else []
    return urls or list(DEFAULT_RPCS)


def host(url):
    """Print only the host name of an endpoint (never a full URL, in case it embeds a key)."""
    return urlparse(url).hostname or "rpc"


class RPCError(Exception):
    pass


class HistoryWindowError(RPCError):
    """Public nodes only serve eth_getLogs for roughly the last ~10,000 blocks (~75 min on BSC)."""


NO_LOGS = ("48.club",)  # default endpoints that reject or time out on eth_getLogs


_cool = {}  # url -> unix time until which we skip it after an error


def rpc(method, params, timeout=20):
    if method not in READ_METHODS:
        raise RPCError(f"method {method} is not allowed (read-only client)")
    last, codes = None, set()
    urls = endpoints()
    if method == "eth_getLogs" and not os.environ.get("BSC_RPC_URLS"):
        urls = [u for u in urls if not any(x in u for x in NO_LOGS)]
    now = time.time()
    ordered = [u for u in urls if _cool.get(u, 0) <= now] + [u for u in urls if _cool.get(u, 0) > now]
    for u in ordered:
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
        req = urllib.request.Request(u, data=body, headers={"Content-Type": "application/json", "User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                out = json.loads(r.read())
        except urllib.error.HTTPError as e:
            last = f"{host(u)} HTTP {e.code}"
            codes.add(e.code)
            _cool[u] = time.time() + (30 if e.code == 429 else 10)
            continue
        except Exception as e:  # timeout, DNS, ...
            last = f"{host(u)} {type(e).__name__}"
            _cool[u] = time.time() + 10
            continue
        if "error" in out:
            last = f"{host(u)} {str(out['error'])[:160]}"
            continue
        return out["result"]
    if method == "eth_getLogs" and codes == {403}:
        raise HistoryWindowError("block range is older than the public nodes' log window (~10,000 blocks); "
                                 "use a smaller --four-lookback or set BSC_RPC_URLS to an archive-capable endpoint")
    raise RPCError(f"all RPC endpoints failed for {method}: {last}")


def block_number():
    return int(rpc("eth_blockNumber", []), 16)


def block_timestamp(n):
    return int(rpc("eth_getBlockByNumber", [hex(n), False])["timestamp"], 16)


def selector(signature):
    return keccak(text=signature)[:4]


def eth_call(to, data):
    if isinstance(data, (bytes, bytearray)):
        data = "0x" + bytes(data).hex()
    return bytes.fromhex(rpc("eth_call", [{"to": to, "data": data}, "latest"])[2:])


def multicall(calls):
    """calls: [(target, calldata_bytes)] -> [(success, return_bytes)] in ONE eth_call via Multicall3.aggregate3."""
    data = selector("aggregate3((address,bool,bytes)[])") + encode(
        ["(address,bool,bytes)[]"], [[(to_checksum_address(t), True, c) for t, c in calls]]
    )
    (res,) = decode(["(bool,bytes)[]"], eth_call(MULTICALL3, data))
    return res


def get_logs(query, from_block, to_block, chunk=5000, min_chunk=50):
    """Chunked eth_getLogs; halves the span when a public node rejects the range."""
    out, b, step = [], int(from_block), int(chunk)
    while b <= to_block:
        e = min(to_block, b + step - 1)
        q = dict(query, fromBlock=hex(b), toBlock=hex(e))
        try:
            out += rpc("eth_getLogs", [q], timeout=15)
            b = e + 1
        except HistoryWindowError:
            raise
        except RPCError:
            if step <= min_chunk:
                raise
            step = max(min_chunk, step // 2)
    return out
