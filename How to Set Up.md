# How to Set Up — instructions for a new AI coding agent

## Objective and defaults

You are setting up **Renko Monthly Weekly**, the source project behind
https://trading.ritishlabs.com/renko-monthly-weekly/ . Set it up on this computer
and leave a working dashboard at **http://127.0.0.1:8838/**. Owner controls are
at **http://127.0.0.1:8838/manage/**.

**Dhan is the owner's preferred broker and the repository default.** Use
`BROKER=dhan` unless the owner explicitly selects FYERS. This repository is a
paper-trading project: broker connections supply prices and contract metadata;
they must never execute real orders. A fresh clone has no account credentials,
production positions, production ledger, or saved production settings.

Complete the credential-free local demo first. Then configure Dhan live market
data if the owner supplies valid credentials. If credentials are unavailable,
leave the demo working and explain what is needed for the live-data paper mode.
Do not claim live data has been verified using synthetic demo prices.

Read this file, `README.md`, `package.json`, `server.js`, `paper.js`,
`local_broker.py`, `dhan_datafeed.py` and `.env.example` before changing code.
`deployment/production-notes.md` documents the original server's history; its
old VPS paths and FYERS default are historical, not prerequisites for localhost.

## Project architecture and strategy

This is a small Node.js server with a Python market-data child process and a
plain HTML/CSS/JavaScript frontend. There is no React, database server, bundler,
Vite, or separate frontend build. Static assets are already in `public/`.

| File | Purpose |
| --- | --- |
| `server.js` | Local HTTP server, feed child, REST state/control routes, durable paper state |
| `paper.js` | Three-bot paper strategy and executable bid/ask fills |
| `public/engine.js` | Traditional Renko, EMA3 and Wilder RSI14 calculations |
| `public/app.js`, `index.html`, `style.css` | Dashboard, chart and ledger |
| `dhan_datafeed.py` | Preferred Dhan v2 stream; NIFTY spot and option depth |
| `local_broker.py` | Standalone Dhan credentials/profile/master parsing; no order methods |
| `datafeed.py` | Optional FYERS feed |
| `vendor/fyers/` | Included FYERS helper source, so no other project checkout is needed |
| `fyers_sdk_compat.py`, `quote_fallback.py` | FYERS decoder correction and labelled spot fallback |
| `demo_feed.py` | Explicitly synthetic, credential-free local demo |
| `config.json` | Exchange holiday list; update for future calendar years |
| `test_paper.js`, `test_server.js` | Node strategy and localhost integration tests |
| `test_*py`, `check_browser.py` | Feed decoder tests and optional browser smoke check |

Three independent paper bots use NIFTY spot Renko:

1. Sell bot: one-minute closes, 16.7-point bricks, ATM option sell with a
   500-point hedge. Bullish sells PE; bearish sells CE.
2. Fast buy bot: one-second closes by default (45-second setting available),
   8.6-point bricks, buys a 200-point ITM CE/PE.
3. Minute buy bot: one-minute closes, 16.7-point bricks, buys a 200-point ITM CE/PE.

Stable ledger IDs are 0=sell, 1=fast buy, 2=minute buy; visual order differs.
EMA3 high/low, Wilder RSI14 and two-brick reversal apply. RSI warm-up requires
15 confirmed bricks. Entry eligibility is 09:20–15:09 IST on configured trading
days; wall-clock square-off is 15:10. Each leg uses one current broker lot.
Fresh depth and sufficient displayed size are required. Buys fill at ask; sells
at bid. Missing exit depth keeps an exit pending. Costs are configurable
estimates and default to zero. Do not invent fills, missing candles or old trades.

## 1. Install the required toolkit

Detect the OS and existing tools first. Reuse suitable installed versions.

Required:

- **Git** to clone the repository (unnecessary if a ZIP was already downloaded).
- **Node.js 22.9 or newer**, including **npm**. A current supported Node LTS
  release is also suitable. The start command uses Node's optional env-file flag.
- **Python 3.12 or newer**, with `venv` and `pip`.
- A browser. An internet connection is needed to install packages and, for live
  broker mode, to access the broker API/WebSocket and instrument master.

Not needed for local operation: GitHub CLI, a GitHub PAT, Docker, Nginx,
PostgreSQL, Redis, a cloud server, a public domain, TLS certificates or a static
public IP configured by this project. Codex is the setup agent; no OpenAI API
key is needed by the application. Do not install a second Codex just to run it.

Install missing tools through an official installer or the computer's package
manager. Examples:

- Windows PowerShell: `winget install Git.Git`,
  `winget install OpenJS.NodeJS.LTS`, `winget install Python.Python.3.12`.
  Open a new terminal after installation so PATH is refreshed.
- macOS with Homebrew already available: `brew install git node python@3.12`.
- Ubuntu/Debian: `sudo apt-get update` then
  `sudo apt-get install -y git curl ca-certificates python3 python3-venv python3-pip`.
  Check versions; older distributions may need a supported Python package or
  upgrade. Do not assume the distribution's `nodejs` package is recent enough.
  If nvm is already installed, `nvm install 22` and `nvm use 22` installs an
  appropriate Node. Otherwise use the official Node download instructions for
  this machine: https://nodejs.org/en/download .

Verify `git --version`, `node --version`, `npm --version`, and
`python3 --version` (Windows: `py -3.12 --version`). Use the appropriate Python
executable in the commands below. No systemwide npm packages are required.

## 2. Clone or open this repository

If not already downloaded:

```sh
git clone https://github.com/ritish07/renko-monthly-weekly.git
cd renko-monthly-weekly
```

If it is private, use the computer's existing GitHub authentication; obtain
read access from the owner if required. Never embed a PAT in a remote URL or a
project file. If already inside a downloaded checkout, do not clone a second copy.
Run all subsequent commands from the repository root.

## 3. Create an isolated Python environment and install dependencies

Linux/macOS:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
npm ci
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm ci
```

`requirements.txt` installs the Dhan WebSocket dependency. No Dhan SDK is
required: the Dhan adapter uses the documented wire protocol, Python's HTTP
library and the `websockets` package. Node has no external runtime dependencies;
`npm ci` verifies its lockfile. You do not have to activate the Python environment:
the server finds `.venv/bin/python` or `.venv/Scripts/python.exe` automatically.
Set `PYTHON_BIN` to an absolute Python executable only if an override is needed.

## 4. Start and verify the credential-free demo

```sh
npm run demo
```

Leave this process running in a terminal/background session. Open:

- Dashboard: http://127.0.0.1:8838/
- Owner controls: http://127.0.0.1:8838/manage/
- Health/state JSON: http://127.0.0.1:8838/api/state

Verify the JSON has `broker: "DEMO"`, `execution: "PAPER"`, a changing `spot`,
three `bricks` arrays and three `pending` entries. The page must display
**SYNTHETIC DEMO**. It is not a broker or live-market verification. Real clock
and strategy-session/warm-up restrictions remain in the demo, so an immediate
paper trade is not an acceptance criterion.

The public route hides controls. `/manage/` exposes local start/stop/settings.
Local controls work only on a loopback host/connection with the control header
and matching Origin when present. Local mode is not a replacement for remote
authentication; do not expose the development server to the internet.

If 8838 is occupied, choose a free port: Linux/macOS `PORT=8839 npm run demo`;
PowerShell `$env:PORT='8839'; npm run demo`. Update browser/check URLs accordingly.
Do not stop unrelated services to free the default port. Ctrl+C stops the server
and its feed; the paper ledger persists.

## 5. Configure Dhan live market data — preferred

Stop the demo before starting another server on the same port. Copy
`.env.example` to `.env` (`cp .env.example .env`, or PowerShell
`Copy-Item .env.example .env`) and set:

```dotenv
BROKER=dhan
DHAN_CLIENT_ID=YOUR_DHAN_CLIENT_ID
DHAN_ACCESS_TOKEN=YOUR_CURRENT_DHAN_ACCESS_TOKEN
PORT=8838
```

The owner must provide their own matching client ID/token and a Dhan account
with the required live market-data entitlement. Generate/manage the token in
the owner's Dhan account; this project does not automate login, OTP, payment,
subscription purchase or renewal. Authentication and data entitlement are
external prerequisites. Do not substitute example values or request a GitHub
PAT for broker authentication. Do not print full tokens in terminal output.

As an alternative to tokens in `.env`, set `DHAN_CREDENTIALS_FILE` to an absolute
private JSON path containing `{"client_id":"...","access_token":"..."}`.
File values override matching environment values. Protect it with owner-only
permissions on Unix (`chmod 600`). Credential changes are rechecked; restarting
after updating `.env` is required to reload the process environment.

Run:

```sh
npm start
```

This starts **Dhan live data with paper fills**, not real trading. Confirm
`broker: "DHAN"` and `execution: "PAPER"` in `/api/state`. Profile verification
and the current instrument master should load. During market hours, verify
fresh NIFTY spot and option bid/ask depth. Outside market hours, a waiting/closed
state is expected and is not a reason to replace real data with synthetic data.
Test the local demo separately if you need a moving UI outside market hours.

The Dhan worker reads the current NIFTY master daily, subscribes to requested
options plus spot, reconnects on stale spot/disconnect/token changes, and reports
errors without revealing token values. It does not expose order endpoints.
Keep the computer clock synchronized; all exchange sessions are evaluated in
Asia/Kolkata/IST even if this computer uses another timezone.

Official Dhan references: [authentication](https://dhanhq.co/docs/v2/authentication/),
[live feed](https://dhanhq.co/docs/v2/live-market-feed/), and
[account/API access](https://dhan.co/support/platforms/dhanhq-api/how-to-access-dhan-api/).

## 6. FYERS alternative — only when explicitly selected

Default to Dhan. If the owner asks for FYERS:

1. Install `requirements-fyers.txt` using the same virtual environment.
2. Create `.secrets/fyers/credentials.json` containing
   `{"app_id":"YOUR_APP_ID","access_token":"YOUR_CURRENT_ACCESS_TOKEN"}`.
   The app ID is the API app ID including its broker-required suffix. The token
   must be issued for that app/account. Do not prepend the app ID to the token
   value; the adapter forms the authorization header.
3. Set `BROKER=fyers` in `.env`. Set `FYERS_CREDENTIALS_DIR` only if using another
   absolute private directory containing `credentials.json`.
4. Run `npm start` and verify `broker: "FYERS"` / `execution: "PAPER"`.

All required helper source is included in `vendor/fyers`; never look for another
checkout under `/opt`. This repository does not include a broker login UI for
issuing a new token. The original service's external login URL is historical.
The FYERS SDK compatibility fix applies only inside this process. Stream outages
can use a labelled spot snapshot fallback; option depth still must be fresh.

## 7. Tests and optional browser tooling

Always run:

```sh
npm test
.venv/bin/python -m unittest -v test_dhan_feed test_quote_fallback
```

On Windows replace `.venv/bin/python` with `.\.venv\Scripts\python.exe`.
Node tests include an isolated localhost demo, public-control rejection,
cross-origin rejection, owner controls and paper-state persistence. Test data
uses a temporary directory and no broker credentials.

If FYERS dependencies are installed, also run:

```sh
.venv/bin/python -m unittest -v test_fyers_sdk_compat
```

Optional browser verification (not needed to run the app):

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m playwright install chromium
# On Linux, if Chromium's OS libraries are missing:
# .venv/bin/python -m playwright install --with-deps chromium
```

Start `npm run demo` in another terminal, then:

```sh
.venv/bin/python check_browser.py
```

The check tests desktop/mobile layout and local demo owner controls. It rejects
non-loopback URLs. If using a different port, set `CHECK_BASE_URL` accordingly.
Screenshots go in ignored `.data/browser-check/`. A preinstalled browser can be
selected with `PLAYWRIGHT_CHROMIUM_EXECUTABLE`; no machine-specific browser path
is hardcoded into the checker.

## 8. Storage, restart and troubleshooting

Default paper ledgers are separated by mode:

- `.data/dhan/paper.json`
- `.data/fyers/paper.json`
- `.data/demo/paper.json`

`RENKO_DATA` overrides the state directory. Do not point two running processes
at the same directory, and do not reuse a demo ledger for broker mode. Paper
settings, open positions and pending exits survive restart; Renko warm-up
restarts. Stop the process before backing up or deliberately resetting state.
Never delete an existing ledger as a routine setup step.

| Symptom | What to check |
| --- | --- |
| `node` missing/optional env-file flag rejected | Install Node >=22.9 and reopen terminal |
| Python/`websockets` missing | Use the repository venv and install requirements |
| Cannot start Python child | Verify `.venv` or absolute `PYTHON_BIN`; no `/opt` path is required |
| Browser cannot connect | Check server logs, loopback URL, chosen port and process lifetime |
| Owner controls hidden | Use the trailing-slash `/manage/` URL, not the public route |
| Owner command rejected | Use localhost directly, matching Origin and default loopback binding |
| Authentication unavailable | Verify current token/client ID, account match and data entitlement |
| No live quotes outside session | Expected; run explicitly labelled demo for a UI smoke check |
| No trades yet | Check fresh depth, requested contracts, session, warm-up and signal eligibility |
| Pending exit / P&L unavailable | Wait for fresh executable quotes; never invent an exit price |
| Instrument master unavailable | Check internet/TLS/broker availability; retry without fabricated contracts |
| Future holiday/calendar issue | Update `config.json` from the exchange's authoritative calendar |

The server runs while its process runs; the browser can close independently.
For an always-on local machine use the OS's process manager only if requested.
`renko-monthly-weekly.service` and `nginx.conf` are deployment examples for the
original Linux reverse-proxy environment; they are unnecessary for localhost.
`npm run start:production` retains trusted-proxy owner authentication and does
not enable local owner bypass. Adapt paths/authentication deliberately before
any remote deployment. Never overwrite another working production service.

## Completion report expected from the coding agent

Report the exact dashboard and owner URLs, commands used, tests passed, state
directory, chosen broker, and whether verification used demo or authenticated
live market data. If credentials or an open market are unavailable, say so
clearly while leaving the local demo usable. Keep the server running in an
appropriate background terminal if the user asked to use it now.

Do not enable real execution, alter strategy rules, push private credentials,
change production hosting, or delete paper history as part of a local setup.
