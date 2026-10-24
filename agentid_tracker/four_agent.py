"""Four.meme "Binance Agent ID Exclusive" zone (OpenFour engine) - read-only.

Every Agent-ID token is created by OpenFourCore with presetId 1778027615735. Two events tell us
everything we need:
  TokenCreated(requestId, presetId idx, creator idx, token idx, name, symbol, maxSupply, saleAmount,
               raiseAmount, ...)                       -> new launch
  TradeExecuted(token idx, trader idx, presetId idx, isBuy, ..., totalRaised, remainingForSale)
                                                       -> curve fill = totalRaised / raiseAmount
Source: official docs github.com/four-meme-community/openfour-docs (Binance Agent ID Exclusive guide).
"""
from eth_abi import decode
from eth_utils import keccak, to_checksum_address

from . import rpc as R

CORE = "0xebe7b6C1089D9F72aD07f34E36d898e44E5e27f3"  # OpenFourCore
PRESET = 1778027615735                               # "Binance Agent ID Exclusive"
PRESET_TOPIC = "0x" + PRESET.to_bytes(32, "big").hex()
T_CREATED = "0x" + keccak(text="TokenCreated(uint256,uint256,address,address,string,string,uint256,uint256,uint256,uint256,address,address,address,address,address,address,address,string,uint256,bytes)").hex()
T_TRADE = "0x" + keccak(text="TradeExecuted(address,address,uint256,bool,address,address,uint256,uint256,uint256,uint256,uint256,uint256,uint256,uint256,uint256,uint256,uint256,uint256)").hex()
# Four's own pre-launch test tokens were created by this address (public on-chain data); flagged, not hidden.
KNOWN_TEST_CREATORS = {"0xaefa15a31bea077b7e388432e1751f79e3ff3632"}

TC_TYPES = ["uint256", "string", "string", "uint256", "uint256", "uint256", "uint256", "address", "address", "address",
            "address", "address", "address", "address", "string", "uint256", "bytes"]
TC_KEYS = ["requestId", "name", "symbol", "maxSupply", "saleAmount", "raiseAmount", "initialPrice", "quoteAsset", "vault",
           "curveModule", "tradeModule", "migrateModule", "customData", "tokenModule", "tokenMetaUri", "flags", "encodedTags"]
TE_TYPES = ["bool", "address", "address"] + ["uint256"] * 12
TE_KEYS = ["isBuy", "quoteAsset", "vault", "requestedTokenAmount", "tokenAmount", "curveQuoteAmount", "traderQuoteAmount",
           "lastPrice", "slippageLimit", "protocolFee", "taxFee", "devFee", "antiSniperFee", "totalRaised", "remainingForSale"]


def _created(log):
    d = dict(zip(TC_KEYS, decode(TC_TYPES, bytes.fromhex(log["data"][2:]))))
    creator = to_checksum_address("0x" + log["topics"][2][-40:])
    token = to_checksum_address("0x" + log["topics"][3][-40:])
    return {"token": token, "creator": creator, "name": d["name"], "symbol": d["symbol"],
            "raiseAmount": d["raiseAmount"], "saleAmount": d["saleAmount"], "block": int(log["blockNumber"], 16),
            "tx": log["transactionHash"], "test": creator.lower() in KNOWN_TEST_CREATORS}


def _trade(log):
    d = dict(zip(TE_KEYS, decode(TE_TYPES, bytes.fromhex(log["data"][2:]))))
    return {"token": to_checksum_address("0x" + log["topics"][1][-40:]),
            "trader": to_checksum_address("0x" + log["topics"][2][-40:]),
            "isBuy": d["isBuy"], "totalRaised": d["totalRaised"], "block": int(log["blockNumber"], 16)}


class FourAgentScanner:
    """Incremental scanner: call update() repeatedly; it remembers the last scanned block."""

    MAX_PUBLIC_LOOKBACK = 9000   # public nodes keep ~10k blocks of logs

    def __init__(self, lookback_blocks=5000):
        self.tokens = {}       # token -> record
        self.last_block = None
        self.lookback = lookback_blocks

    def update(self):
        head = R.block_number()
        frm = head - self.lookback if self.last_block is None else self.last_block + 1
        if head - frm > 2000 and self.last_block is not None:   # long pause: skip ahead instead of hammering old ranges
            frm = head - 2000
        if frm > head:
            return []
        new = []
        for log in R.get_logs({"address": CORE, "topics": [T_CREATED, PRESET_TOPIC]}, frm, head):
            c = _created(log)
            if c["token"] not in self.tokens:
                c.update(buyers=set(), buys=0, sells=0, totalRaised=0)
                self.tokens[c["token"]] = c
                new.append(c["token"])
        for log in R.get_logs({"address": CORE, "topics": [T_TRADE, None, None, PRESET_TOPIC]}, frm, head):
            t = _trade(log)
            tok = self.tokens.get(t["token"])
            if not tok:
                continue  # created before our lookback window
            if t["isBuy"]:
                tok["buys"] += 1
                if t["trader"] != tok["creator"]:
                    tok["buyers"].add(t["trader"])
            else:
                tok["sells"] += 1
            tok["totalRaised"] = t["totalRaised"]
        self.last_block = head
        return new

    def rows(self):
        out = []
        for tok in self.tokens.values():
            fill = 100.0 * tok["totalRaised"] / tok["raiseAmount"] if tok["raiseAmount"] else 0.0
            out.append({
                "venue": "four_agent", "id": tok["token"], "name": tok["name"], "symbol": tok["symbol"], "quote": "BNB",
                "fill_pct": round(fill, 2), "raised": round(tok["totalRaised"] / 1e18, 4),
                "cap": round(tok["raiseAmount"] / 1e18, 4), "buys": tok["buys"], "sells": tok["sells"],
                "unique_buyers": len(tok["buyers"]), "creator": tok["creator"], "launched": fill >= 100.0,
                "test_token": tok["test"], "block": tok["block"], "link": f"https://four.meme/token/{tok['token']}",
            })
        return out
