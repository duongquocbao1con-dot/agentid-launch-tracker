# agentid-launch-tracker

A small, **read-only** Python tool + tutorial for tracking **Agent-ID-gated token launches on BNB Chain**:

| Venue | What it is | How the tool reads it |
|---|---|---|
| **flap.sh ID Agent Curve** (primary) | flap mini app: pre-launch bonding-curve markets that only Binance Agent ID (.ai) holders can buy; at 100 % the token launches on flap | `eth_call` to the app's Factory + Reader contracts (one Multicall3 call per batch) |
| **Four.meme Agent ID zone** | OpenFour preset "Binance Agent ID Exclusive" | `eth_getLogs` on OpenFourCore `TokenCreated` / `TradeExecuted` filtered by presetId |
| **GANG.fun** | agent-only launchpad, 20 BNB to graduate | public JSON API |

Features

- detects **new Agent-ID launches** on each venue
- shows **curve fill %** (raised / cap), buys/sells, quote token
- simple, transparent **creator reputation** (earlier launches, graduation rate, spam / dead-launcher flags)
- **alerts** to stdout and/or any **webhook** (Discord-compatible): `new_launch`, `fast_fill` (+10 pp in 2 min by default), `near_full` (80 % / 95 %), `launched`

What it does **not** do: no wallet, no signing, no transactions, no buy/sell code, no API keys.
It only uses public read methods (`eth_blockNumber`, `eth_call`, `eth_getLogs`, `eth_getBlockByNumber`) and public HTTP APIs.
Nothing here is financial advice.

## Quick start

```bash
git clone <this repo> && cd agentid-launch-tracker
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

python -m agentid_tracker snapshot                 # one-shot table of all venues
python -m agentid_tracker snapshot --venues flap --all --top 30
python -m agentid_tracker watch --interval 15      # poll forever, print alerts
python -m agentid_tracker watch --json --webhook https://discord.com/api/webhooks/...   # alerts to a webhook
python -m agentid_tracker creator 0xCreatorAddress # reputation of one creator
python -m agentid_tracker rpc-check                # which RPC endpoints are used
python -m unittest discover -s tests               # offline tests
```

Configuration (all optional, environment variables):

| Variable | Default | Meaning |
|---|---|---|
| `BSC_RPC_URLS` | `https://bsc-rpc.publicnode.com,https://rpc-bsc.48.club,https://bsc.publicnode.com` | comma-separated JSON-RPC endpoints, tried in order |
| `ALERT_WEBHOOK_URL` | (none) | webhook that receives `{"content": "...", "event": {...}}` |

Note: public BSC nodes only serve `eth_getLogs` for roughly the **last ~10,000 blocks (~75 min)**, so the Four
scanner starts with `--four-lookback 5000` (max ~9000 on public nodes). For older history point `BSC_RPC_URLS` at an
archive-capable endpoint of your choice.

## Example output

See [`examples/`](examples/). A real run on 24 Oct 2026 (UTC+7):

```
== flap_agent_curve: 70 launches seen, 59 still on the curve, 11 launched/graduated ==
  FANG           ##..................   8.22% 0.4114/5.0 BNB   creator_score= -2  https://flap.sh/apps/agent-bonding-curve market=0xfd0d…98c4
  智能时代        ##..................   7.64% 1.1534/15.083 NVDAB creator_score= -1  …
== four_agent: 0 launches seen, 0 still on the curve, 0 launched/graduated ==
== gang: 43 launches seen, 42 still on the curve, 1 launched/graduated ==
  GDOG           ###########.........  56.12% 11.2256/20.0 BNB   creator_score=  0  https://gang.fun/token/0xf050…3c4e
```

## Tutorial

**[docs/TUTORIAL.md](docs/TUTORIAL.md): How Agent ID launches on flap.sh work and how to track them.** It goes step by step
from "what is an Agent ID" to reading the curve contracts with ~20 lines of Python.

## Project layout

```
agentid_tracker/
  rpc.py          read-only JSON-RPC client, public endpoint fallback, Multicall3, chunked getLogs
  flap_curve.py   flap.sh ID Agent Curve: markets, cards (fill %), creators
  four_agent.py   Four.meme Agent ID zone: TokenCreated / TradeExecuted scanner
  gang.py         GANG.fun public API
  reputation.py   creator reputation score
  tracker.py      polling + diff -> events
  alerts.py       stdout / webhook alerts
  cli.py          command line
docs/TUTORIAL.md  step-by-step tutorial
examples/         real output captured from public RPC
tests/            offline unit tests
```

## Safety notes

- Same names are reused all the time (several "bibi", "AGENT OS", "帮派"). Always use the **market / token address**
  read from the venue's own contracts, never a name or a link from a reply.
- A positive creator score is a weak hint; most creators are new and score 0. A negative score is a warning light.
- Fill % moves fast on small caps (5 BNB). Alerts are information, not signals to buy.

---

## Tóm tắt tiếng Việt

**agentid-launch-tracker** là công cụ Python **chỉ đọc** (không ví, không ký, không giao dịch, không cần API key) để theo dõi
các đợt ra mắt token chỉ dành cho người có **Agent ID** trên BNB Chain: **flap.sh ID Agent Curve** (chính), khu Agent ID của
**Four.meme** và **GANG.fun**. Công cụ phát hiện market mới, hiển thị % lấp đầy bonding curve, chấm điểm uy tín người tạo
và gửi cảnh báo ra màn hình hoặc webhook (Discord...). Dùng RPC công khai (mặc định publicnode), cấu hình qua biến môi trường
`BSC_RPC_URLS`. Hướng dẫn từng bước: [docs/TUTORIAL.md](docs/TUTORIAL.md). Không phải lời khuyên đầu tư.

## 中文摘要

**agentid-launch-tracker** 是一个**只读**的 Python 工具和教程（不需要钱包、不签名、不发交易、不需要 API 密钥），
用于追踪 BNB Chain 上**仅限 Agent ID 持有者**参与的代币发射：**flap.sh ID Agent Curve**（主要）、**Four.meme** Agent ID 专区
和 **GANG.fun**。功能：发现新市场、显示联合曲线填充进度、创建者信誉评分、终端或 Webhook（如 Discord）提醒。
默认使用公共 RPC（publicnode），可通过环境变量 `BSC_RPC_URLS` 配置。分步教程见 [docs/TUTORIAL.md](docs/TUTORIAL.md)。
本项目不构成投资建议。

## License

MIT, see [LICENSE](LICENSE). Built by [@BNguyen66900](https://x.com/BNguyen66900) with help from an AI coding assistant.
