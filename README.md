# Renko Monthly Weekly

Three NIFTY Renko paper bots with a browser dashboard and durable local paper ledger.
**Dhan is the preferred/default broker.** FYERS is optional. All fills are paper only.

Start here: [How to Set Up.md](How%20to%20Set%20Up.md). The guide is written for a new AI coding agent setting up a fresh computer, including Windows, macOS and Linux commands, credentials, dependencies, validation and troubleshooting.

## Quick start

Install Node.js >=22.9, Python >=3.12 and Git. From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
npm ci
npm run demo
```

Open **http://127.0.0.1:8838/**. Local owner controls: **http://127.0.0.1:8838/manage/**.
The demo is explicitly synthetic and needs no broker credentials. On Windows use `py -3.12` and `.\.venv\Scripts\python.exe` as documented in the setup guide.

For real Dhan prices with paper execution, stop the demo, copy `.env.example` to `.env`, set your own `DHAN_CLIENT_ID` and `DHAN_ACCESS_TOKEN`, keep `BROKER=dhan`, and run `npm start`. Valid broker credentials and market-data access are required. A closed market or missing quotes will show a waiting state. No real orders are submitted.

## Strategies

| Bot | Spot close interval | Renko brick | Position |
| --- | --- | --- | --- |
| Sell | 1 minute | 16.7 points | ATM short option plus 500-point hedge |
| Buy minute | 1 minute | 16.7 points | 200-point ITM CE/PE |
| Buy fast | 1 second; optional 45 seconds | 8.6 points | 200-point ITM CE/PE |

EMA3 high/low, Wilder RSI14, confirmed-brick signals and two-brick reversals. Fresh executable option depth is required. One current broker lot per leg. Entry window 09:20–15:09 IST; square-off 15:10. Missing exit depth remains pending. Costs are estimates, default zero.

## Validation

```sh
npm test
.venv/bin/python -m unittest -v test_dhan_feed test_quote_fallback
```

Optional FYERS and browser requirements/checks are described in the setup guide.
The frontend is plain JavaScript: no bundler or separate build is needed.

`.env`, `.secrets/`, `.data/` and `.venv/` are ignored. Default demo/Dhan/FYERS state directories are separate. The repository contains no production credentials, account ledgers or GitHub tokens.

Original hosted project: https://trading.ritishlabs.com/renko-monthly-weekly/ .
The portable checkout does not modify that server. Original deployment history is archived in [deployment/production-notes.md](deployment/production-notes.md).
