# How Agent ID launches on flap.sh work, and how to track them

This tutorial explains the **flap.sh "ID Agent Curve"** launch format on BNB Chain and shows, step by step, how to read
it straight from the chain with a few lines of Python. At the end we compare it with the two other Agent-ID-gated venues
(Four.meme's Agent ID zone and GANG.fun) and run the full tracker.

Everything here is **read-only**: we never connect a wallet, sign, or send a transaction. Numbers marked *observed* were
measured on 23–24 Oct 2026 and may change; always check the app page.

---

## 1. What is an "Agent ID"?

- Binance Wallet's **Agentic Wallet** lets an AI agent (Binance AI "Bibi") act for a user. Each agent can claim a free
  **Agent ID**: a `.ai` name issued as an NFT by SPACE ID.
- On BNB Chain the Agent ID NFT contract is `0x60B9262456dE011F7d15a54CdD8c48bAaa8B022F`.
  "Holds an Agent ID" simply means `balanceOf(wallet) > 0` on that contract.
- Several launchpads use this NFT as a **gate**: only agent wallets can buy during the bonding-curve phase. The idea is to
  keep the early curve away from ordinary sniper bots and give agents a fair start.

## 2. The flap.sh ID Agent Curve in one picture

```
 create market ──► curve phase (phase 1) ──────────────► pool hits cap ──► token launches on flap (phase 3)
 (anyone, pays     only Agent ID holders can buy          (5 BNB for BNB      holders claim 1:1, token is
  a small fee)     shares, via Bibi chat                   markets)           tradable by everyone on DEX
```

- It is the first flap **mini app**: <https://flap.sh/apps/agent-bonding-curve> (opened 23 Oct 2026, 21:21 UTC+7).
- A market is a **pre-launch share market** on a bonding curve. Shares are ledger positions, not tokens yet, and cannot be
  transferred. *Observed:* max 2 % of a market per wallet, and Bibi's mini-app limit of 1 BNB per transaction.
- Each market has a **quote token** and a **cap**. *Observed caps:* 5 BNB (BNB markets), ~666.5 BNCB, ~15.08 NVDAB,
  ~4.94 QQQB. Progress = pool / cap.
- When progress reaches 100 % the real token is deployed on flap (a normal flap token whose address usually ends in
  `7777`), the market switches to **phase 3**, and buyers **claim 1:1**. From then on anybody can trade it.
- First-day stats (*observed* 24 Oct 00:20 UTC+7): 62 markets, 10 launched. By 24 Oct 17:15 UTC+7 there were 70 markets
  and 11 launched.

## 3. The contracts

The app's public manifest lists two contracts we need:

| Contract | Address | Useful read functions |
|---|---|---|
| Factory | `0xC55820f24015bE7c4f18949D9e1363A3609B300e` | `marketCount()`, `markets(uint256 i)` |
| Reader | `0x18Aa6C93f1887a243fdc348C9A77F5136555174a` | `marketCards(address[] markets)` (≤5 per call), `marketDetail(address market)` |

`marketCards` returns, for each market, a tuple:

```
(market, quoteToken, name, symbol, meta, predictedToken, token, pair, phase,
 poolRaw, capRaw, progressBps, buyCount, sellCount, curveH, curveK)
```

- `phase` 1 = curve, 3 = launched; `token` is zero until launch.
- `progressBps / 100` = fill %; `poolRaw / 1e18` and `capRaw / 1e18` = raised and cap in quote units.
- In `marketDetail(market)` the second 32-byte word is the **creator** address.

## 4. Step by step in Python

Install two small libraries: `pip install eth-abi eth-utils "eth-hash[pycryptodome]"`.

### Step 1: a JSON-RPC call to a public node

```python
import json, urllib.request
RPC = "https://bsc-rpc.publicnode.com"          # free public endpoint, no key

def rpc(method, params):
    req = urllib.request.Request(RPC, data=json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
        headers={"Content-Type": "application/json",
                 "User-Agent": "agentid-tutorial"})   # some public nodes reject the default Python user agent
    return json.loads(urllib.request.urlopen(req, timeout=20).read())["result"]

print(int(rpc("eth_blockNumber", []), 16))       # current block
```

### Step 2: build calldata and read the number of markets

A contract call is just `selector + ABI-encoded arguments`, where selector = first 4 bytes of `keccak("fn(types)")`.

```python
from eth_abi import encode, decode
from eth_utils import keccak
FACTORY = "0xC55820f24015bE7c4f18949D9e1363A3609B300e"
READER  = "0x18Aa6C93f1887a243fdc348C9A77F5136555174a"
sel = lambda sig: keccak(text=sig)[:4]

def call(to, data):
    return bytes.fromhex(rpc("eth_call", [{"to": to, "data": "0x" + data.hex()}, "latest"])[2:])

n = decode(["uint256"], call(FACTORY, sel("marketCount()")))[0]
markets = [decode(["address"], call(FACTORY, sel("markets(uint256)") + encode(["uint256"], [i])))[0]
           for i in range(n)]
print(n, "markets; newest:", markets[-1])
```

### Step 3: read the cards (fill %)

```python
CARD_T = "(address,address,string,string,string,address,address,address,uint8,uint256,uint256,uint256,uint256,uint256,uint256,uint256)[]"
for i in range(0, len(markets), 5):                       # Reader accepts up to 5 markets per call
    raw = call(READER, sel("marketCards(address[])") + encode(["address[]"], [markets[i:i+5]]))
    for c in decode([CARD_T], raw)[0]:
        name, symbol, phase, pool, cap, bps = c[2], c[3], c[8], c[9], c[10], c[11]
        state = "launched" if phase >= 3 else "curve"
        print(f"{symbol:<12} {bps/100:6.2f}%  {pool/1e18:.4f}/{cap/1e18:.4f}  {state}")
```

That is the whole core of a tracker. Poll it every 10–15 s and compare with the previous result.

### Step 4: fewer requests with Multicall3

Calling one market at a time is slow and may hit public rate limits. `Multicall3`
(`0xcA11bde05977b3631167028862bE2a173976CA11`, same address on every EVM chain) bundles many reads into **one**
`eth_call`:

```python
def multicall(calls):  # calls = [(target, calldata)]
    data = sel("aggregate3((address,bool,bytes)[])") + encode(["(address,bool,bytes)[]"], [[(t, True, d) for t, d in calls]])
    return decode(["(bool,bytes)[]"], call("0xcA11bde05977b3631167028862bE2a173976CA11", data))[0]
```

The tracker reads all ~70 markets (cards + creators) in 3–4 RPC calls this way.

### Step 5: who created the market?

```python
raw = call(READER, sel("marketDetail(address)") + encode(["address"], [markets[-1]]))
creator = "0x" + raw[44:64].hex()          # word 1 = creator
```

With every market's creator we can build a small **reputation** table: how many markets this address created before,
how many launched, and whether it spams (see `agentid_tracker/reputation.py`). Most creators are new (score 0). The
useful part is the warning side: an address that has opened 5+ markets, or 3+ that never passed 30 %.

### Step 6: alerts

The tracker keeps a short history of fill % per market and emits:

| Event | Rule (defaults) |
|---|---|
| `new_launch` | a market/token appears that was not in the previous poll |
| `fast_fill` | fill rose ≥ 10 percentage points within 120 s |
| `near_full` | fill crossed 80 % or 95 % |
| `launched` | phase changed to launched / graduated |

Each alert is printed and, if `ALERT_WEBHOOK_URL` is set, POSTed as JSON (`{"content": ..., "event": {...}}`), which a
Discord webhook accepts as-is.

## 5. The other Agent-ID venues

| | flap.sh ID Agent Curve | Four.meme Agent ID zone | GANG.fun |
|---|---|---|---|
| Gate | Agent ID NFT, buy via Bibi | Agent ID NFT **and** a per-preset whitelist switch | Agent ID / agentic wallet |
| Cap / graduation | 5 BNB (or quote equivalent) | `raiseAmount` per token (*observed* ≈13.5 BNB) | 20 BNB |
| After cap | token deployed on flap, claim 1:1 | migrates to PancakeSwap V2 | graduates to DEX |
| How to read | Factory/Reader `eth_call` | OpenFourCore `0xebe7…27f3` events, presetId `1778027615735` | public API `gang.fun/api/tokens` |

**Four.meme** runs Agent tokens on its modular OpenFour engine. One `eth_getLogs` filter on OpenFourCore with
`topic0 = TokenCreated` and `topic1 = presetId` finds every Agent launch; `TradeExecuted` (presetId in topic 3) gives
`totalRaised`, so fill % = `totalRaised / raiseAmount`. *Observed* 24 Oct: only Four's own test tokens existed and the
whitelist gate was on, so the tracker shows 0 live tokens there until Four opens the zone.

Public nodes keep only ~10,000 blocks (~75 min) of logs, so the Four scanner looks back 5,000 blocks by default and then
follows new blocks.

## 6. Run the full tracker

```bash
pip install -r requirements.txt
python -m agentid_tracker snapshot                    # table for all three venues
python -m agentid_tracker watch --interval 15         # alerts forever (Ctrl+C to stop)
ALERT_WEBHOOK_URL=https://discord.com/api/webhooks/... python -m agentid_tracker watch
```

## 7. Safety checklist

1. **Names are not unique.** There are several "bibi", "AGENT OS" and "FStock" markets. Use the address from the
   Factory/Reader, never a name.
2. **After launch, copycat pools appear** with the same name and high tax. Take the token address from the market's own
   `token` field (Reader) and check the tax before trading anything.
3. A high fill % on a 5 BNB cap can come from very few wallets. Check buys vs sells and the creator score.
4. This tool and tutorial are educational. They are not financial advice.

## 8. Ideas to extend

- Wallet-level buys: the curve markets emit a labelled event (topic0 `0x0483a030…8aed`) whose first word is the ASCII
  label `virtualBuyFill`, followed by sequence, wallet, token, amount, shares (*observed*, reverse-engineered, not
  documented). You can add it to show unique buyers per market.
- Post-launch tracking with DexScreener's public API (`api.dexscreener.com/tokens/v1/bsc/<addresses>`).
- A Telegram bot instead of a webhook.
