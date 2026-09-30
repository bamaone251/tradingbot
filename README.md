# Strategy Trader

A small Flask app + daily scheduler that watches a list of stocks, runs your
4 backtested strategies against each one, and trades them automatically
through your Alpaca account. Built to run on your own VPS behind nginx, next
to your other self-hosted apps.

**This places real orders once you switch it to live trading. Read the whole
README before you do that, especially "Things this app does NOT do."**

## How it works, in one paragraph

Once a day, shortly after the market closes, the app pulls fresh daily price
bars for every symbol on your watchlist from Alpaca, computes the indicators
each assigned strategy needs (SMA, MACD, RSI, or Bollinger Bands - all
computed locally, no external data dependency), and checks whether that
strategy's condition is met. If a strategy that isn't currently holding a
position sees its buy condition, the app sizes a position (risking a fixed %
of your account equity against an ATR-based stop) and submits a bracket order
(market buy + stop-loss) to Alpaca. If a strategy that IS holding a position
sees its exit condition, the app cancels the stop and sells at market. Every
signal - even the days nothing happens - gets logged.

## Important design decisions (read these)

**Each strategy/symbol pair trades its own independent slice.** If you put
both RSI Mean Reversion and MACD Signal Cross on AAPL, the app tracks them as
two separate positions internally (its own SQLite ledger), even though
Alpaca only shows one combined AAPL position. This means:
- Risk is NOT split between them - each one risks its configured % of your
  *total* account equity, independently. Running many strategies/symbols at
  once stacks risk. Lower each entry's risk % if you're running a lot of
  them concurrently, or keep the total number of active entries in check.
  There's no portfolio-level cap in this version (you told me to skip that
  for now) - it's just the per-trade risk %.
- If you also trade the same symbol manually in the same Alpaca account, the
  app's ledger won't know about your manual shares. Keep manual trading in a
  separate account/symbol set, or expect some confusion in the Positions
  page.

**Entries are bracket orders (market buy + stop-loss), not just a daily
check.** Your backtests size positions with a "Fixed risk % (ATR stop)"
method, which implies the stop is a real risk control, not just a sizing
input. So the app places a real stop-loss order at the broker the moment it
buys, protecting the position intraday - not just once a day when the
scheduler runs. The daily job also checks each strategy's own exit condition
(mid-band, signal cross, RSI overbought, slow-SMA cross) and sells at market
if that fires first.

**Strategy conditions are evaluated as levels, matched to your backtest
descriptions, not crossing events.** E.g. "buy when RSI < 30" fires on the
first day the app checks that this is true *and it isn't already holding
that leg* - not only on the exact day RSI first crosses under 30. This is
simpler and matches the plain-English rule from your backtest configs; it
also means the app won't try to re-buy every single day a condition stays
true, because it only acts when a leg's state (flat vs open) actually needs
to change.

**Trading mode (paper vs live) and API keys are config, not code.** Set them
in `.env` (see below). The dashboard always shows a "Paper" or "LIVE $$$"
badge so you can't lose track of which one you're pointed at.

## Things this app does NOT do (yet)

- No portfolio-level risk caps (max positions, max % deployed, daily loss
  circuit breaker) - you explicitly asked to skip these for the first
  version. Worth revisiting once you've watched it run for a while.
- No login/auth of its own - see the nginx section below, this matters.
- No intraday polling - strategies are evaluated once a day, after close.
- No short selling - all 4 strategies are long-only, matching your backtest
  descriptions.
- No email/push notifications - dashboard only, per what you asked for.
  `app/web.py` and `app/engine.py` are the two places to add a notification
  hook later if you want one.
- Doesn't reconcile against shares you buy/sell manually in the same account
  (see above).

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt      # add -dev for pytest too, if you want to run the tests

cp .env.example .env
# edit .env: paste in your Alpaca PAPER keys (from
# https://app.alpaca.markets/paper/dashboard/overview), leave ALPACA_PAPER=true,
# and set FLASK_SECRET_KEY to something random.

python run.py
```

Then open `http://127.0.0.1:8420` (or whatever `PORT` you set). Go to
**Watchlist**, add a symbol + strategy + risk %, then hit **Run Now** on the
Dashboard to trigger a check immediately instead of waiting for the daily
schedule - this is the fastest way to see it work end to end in paper mode.

## Running the tests

```bash
pip install -r requirements-dev.txt
pytest
```

`tests/test_indicators.py`, `tests/test_sizing.py`, and
`tests/test_strategies.py` check the math (SMA/EMA/RSI/MACD/Bollinger/ATR,
the risk-based position sizing formula, and each strategy's buy/sell logic)
against synthetic price data - no Alpaca connection needed. I ran an
equivalent of this suite while building the app and it all passed; I also ran
a separate integration check of the daily engine (buy → order placed and
position opened correctly, broker-side stop fill → position closed without a
duplicate sell order, strategy exit signal → stop cancelled and market sell
placed) against a faked broker, since I don't have your Alpaca keys.
**I could not test this against your actual Alpaca account or a live network
call to Alpaca's API from here - do that yourself in paper mode before
trusting it with anything.**

## Deploying on your VPS

```bash
# on the VPS
git clone <wherever you put this> trading-bot   # or just upload the folder
cd trading-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in real values
```

Copy `deploy/trading-bot.service` to `/etc/systemd/system/trading-bot.service`,
edit the `YOUR_LINUX_USER` and path placeholders, then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now trading-bot
sudo systemctl status trading-bot
```

**Important: keep `-w 1` (one gunicorn worker) in the service file.** The
daily scheduler lives inside the app process - more than one worker means
more than one scheduler, which means duplicate orders.

Then point nginx at it with `deploy/nginx-trading-bot.conf` as a starting
point (`sudo cp` it into `/etc/nginx/sites-available/`, symlink into
`sites-enabled/`, `sudo nginx -t && sudo systemctl reload nginx`). **This app
has no login of its own** - it's a dashboard that can place real trades, so
at minimum turn on the HTTP basic auth lines in that nginx config before
exposing it beyond `127.0.0.1`, and consider putting it behind your existing
auth if you have something already (a VPN, Tailscale, an existing
nginx-level login) rather than relying on basic auth alone for a live
account.

## Going live

1. Run it in paper mode for a while. Watch the Dashboard and History pages -
   are the signals firing when you'd expect, are the position sizes
   sensible, do stops look right?
2. Generate a **live** API key pair in the Alpaca dashboard (different from
   your paper keys).
3. In `.env`: swap `ALPACA_API_KEY_ID` / `ALPACA_API_SECRET_KEY` to the live
   pair, set `ALPACA_PAPER=false`.
4. Restart the service (`sudo systemctl restart trading-bot`). Check the
   dashboard badge now says **LIVE $$$** in red.
5. Consider starting with small risk % values on your watchlist entries
   while you build confidence, then raise them.

## Project layout

```
app/
  broker.py        Alpaca API wrapper (market data + trading)
  config.py         .env-driven settings
  db.py             SQLite persistence (watchlist, legs, signal log, settings)
  engine.py         The daily job: evaluate every entry, size, place orders
  indicators.py      SMA/EMA/RSI/MACD/Bollinger/ATR, computed with pandas
  sizing.py          Risk-% + ATR-stop position sizing math
  scheduler.py        APScheduler cron job wiring
  web.py            Flask routes / dashboard
  strategies/       One file per strategy (your 4 backtest configs)
  templates/, static/  Dashboard UI
tests/               pytest suite for indicators/sizing/strategies
deploy/              systemd unit + nginx config templates
```
