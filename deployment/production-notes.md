# FYERS NIFTY spot Renko paper workspace

Switched back to FYERS on 2026-10-23 at the owner’s request after Dhan stream timeouts. The dedicated read-only datafeed.py reuses the saved FYERS connection and current FYERS instrument master. It runs in the FYERS Python environment. Paper execution, existing ledger, settings and running state are preserved. No open paper positions existed at the switch. Backup: /root/renko-fyers-switch-20261023/.

FYERS login: https://trading.ritishlabs.com/ritishlabs-index_pro_fyers/

Public dashboard: https://trading.ritishlabs.com/renko-monthly-weekly/
Owner controls: https://trading.ritishlabs.com/renko-monthly-weekly/manage/
Owner route uses the existing Index Pro FYERS Basic Auth login. Public control requests are denied by Nginx and the application.

Historical Dhan configuration (replaced on 2026-10-23): the dhan_datafeed.py process uses the saved server-side Dhan authentication and an isolated read-only WebSocket. Current contracts come from Dhan's instrument master, refreshed daily. Only profile, public master and market data are accessed; no order APIs are called. FYERS was replaced on 2026-10-22 after repeated missing-spot reconnects and an observed HTTP 429. This is a configuration choice based on current failures, not a claim of measured superior live reliability. The previous implementation is backed up under /root/renko-ready-backup-20261022/.

Dhan index packets without an exchange timestamp use observed stream receipt time, explicitly labelled on the dashboard. Timestamped packets and option trade/depth packets must be no more than three seconds old. The socket reconnects after 20 seconds without fresh index data, disconnects, or credential changes. Desired option subscriptions are replaced as ATM changes, including all contracts locked in open positions. Dhan token validity was verified through 2026-10-23 19:10 and its data plan was active. Live session verification remains outstanding because deployment was after market hours.

Both bots are automatically started for this authorized paper run. Start/stop persists. A systemd service runs the engine independently of browsers, survives server reboot, and restarts on process failure. Paper ledger lives in /var/lib/ritishlabs-renko-monthly-weekly/paper.json; writes use fsync and atomic rename. Open positions and pending exits survive restart; Renko warm-up restarts after a service restart or a new trading day. Disconnections and quote gaps retain confirmed bricks and indicators, discard interrupted candles, and pause signals until fresh observations resume. Browser-local demo ledgers are not imported or deleted.

Sell bot: 16.7-point traditional Renko on completed observed one-minute NIFTY spot closes; bullish sells ATM PE and buys ATM-500 PE, bearish sells ATM CE and buys ATM+500 CE. Buying bot: 8.6-point Renko on completed observed one-second closes (owner can select 45 seconds while stopped); bullish buys 200-point ITM CE, bearish buys 200-point ITM PE. Both use the earliest eligible expiry in the current broker master, and one current broker lot per leg, with locked contracts until exit.

EMA3 high/low and Wilder RSI14 are calculated on confirmed bricks, with two-brick reversal. RSI requires 15 confirmed bricks, and warm-up never takes historical/demo trades. Initial partial candles are discarded; missing candles are never fabricated. Quotes in the same exchange second update that second's final observed close. The one-second UI refresh is not a brick-creation timer.

Entries require an authenticated, connected stream, spot and option quotes at most three seconds old, current-day broker master, sufficient displayed size on every leg, and an eligible weekday/non-holiday session 09:20–15:09 IST. EMA-band exits and wall-clock 15:10 square-off use fresh option depth. Stops and square-offs remain pending while quotes are missing, and retry automatically; overdue positions never receive invented end-of-day prices. Overnight expiry without obtainable depth can remain unresolved and needs review.

Paper fills buy at ask and sell at bid. Spread legs are filled atomically by the paper model when all quoted sizes suffice; this does not model real execution latency, queue position, leg risk or market impact. Configurable costs are estimates per leg per fill, default zero, so default P&L excludes actual brokerage and statutory charges. The UI shows unavailable P&L when usable depth is missing.

Commands:
- systemctl status ritishlabs-renko-monthly-weekly
- journalctl -u ritishlabs-renko-monthly-weekly
- node --test /opt/ritishlabs-renko-monthly-weekly/test_paper.js
- /opt/ritishlabs-renko-paper/.test-venv/bin/python /opt/ritishlabs-renko-monthly-weekly/check_browser.py

Original static site backed up to /root/renko-monthly-weekly-before-live/ before modification.

Dashboard body text is 18px; labels, ledger and status text are at least 16px, with stronger contrast. Desktop and 390px mobile browser checks passed. Decoder tests cover index packets, option depth, invalid and stale data.

## FYERS index decoder correction — 2026-10-23

The installed FYERS SDK compared an integer unchanged-field sentinel with a string in its full-mode index delta decoder. This could replace valid NIFTY fields (including price and exchange timestamp) with -2147483648 and cause the fresh-spot watchdog to reconnect. `fyers_sdk_compat.py` corrects only that comparison in memory in this service process; shared broker SDK files and other services are unchanged. It preserves private-name mangling and does nothing when the defective comparison is absent. `test_fyers_sdk_compat.py` feeds real binary delta packet layouts through the decoder and checks that unchanged fields retain their previous values. Run using the FYERS Python environment. The existing three-second freshness gate and paper execution rules remain in force. Backup: `/root/renko-feed-fix-20261023/`.

Socket outages also use a read-only FYERS NIFTY Quotes API snapshot fallback, at most once per second while streamed spot is missing. Responses taking more than two seconds are rejected. FYERS snapshot `tt` is a session date, so accepted snapshots are explicitly labelled by receipt time on the dashboard. No option depth is invented; entries still require fresh streamed option bid/ask and sufficient size. The broker client applies its existing 15-second HTTP 429 cooldown. Snapshot delivery can keep spot observations flowing while option trading remains paused. Missing candles are skipped, never backfilled with invented values. The SDK symbol-token lookup now has a service-local three-second HTTP timeout to prevent the socket supervisor hanging indefinitely.

Validation: 3 Python decoder/snapshot tests and 10 Node paper-engine tests passed. Desktop/mobile browser checks passed. An isolated live FYERS process with `MarketFeed.start` disabled produced three authenticated, fresh REST snapshots, verifying the outage path without touching running bots. Initial decoder-only monitoring still encountered a remote socket disconnect after several minutes; this motivated the timeout, fallback and confirmed-history recovery changes. The final deployed service was checked with fresh spot and 30 option quotes; upstream disconnects can still occur, and entries remain paused if option depth is stale.

## Third bot — 2026-10-29

Added a separate ITM-200 option buying bot on completed one-minute NIFTY spot closes, with 16.7-point Renko and the same EMA3 high/low, Wilder RSI14 and two-brick reversal rules as the selling bot. Bullish buys ATM−200 CE; bearish buys ATM+200 PE. Each bot has independent executable-depth checks, positions, EMA exits and 15:10 square-off. No dependency on whether the selling bot fills. The existing fast buyer remains on 8.6-point bricks and its saved 1/45-second interval.

Stable ledger IDs: 0 = sell 1m; 1 = existing fast buy; 2 = new buy 1m. Dashboard order: sell 1m, buy 1m, fast buy. Existing ledger records retain their IDs and contracts. All three are paper bots, use nearest available expiry and one broker lot per leg, and share the existing start/stop controls and estimated cost setting. Restart resets Renko warm-up; saved positions and exit requests are restored.
