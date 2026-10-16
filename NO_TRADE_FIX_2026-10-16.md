# No-trade diagnostic and discovery prioritization patch (2026-10-16)

Base: `boy_fomo_feed_fallback_paper_exploration.zip`. The bot remains **paper-only**; this patch does not enable signing or place real orders.

## Why the logs reported zero trades

1. `FILTER SUMMARY evaluated=17 eligible=0` — every token failed the hard entry filters, before score/exploration logic. Twelve were too old and five lacked minimum 5m volume. Lowering MIN_SCORE cannot change this.
2. `FRESH FEED unavailable HTTP502` — upstream websocket gateway error. The fresh launch feed cannot be repaired locally if the server remains unavailable. PumpPortal documentation lists the keyed `wss://pumpportal.fun/api/data?api-key=...` connection; if a key is missing, this patch now explicitly logs `reason=missing_api_key` and doesn't repeatedly reconnect. New token event subscriptions are free, but the API key is still required. **Never paste the key in chat or commit it in a ZIP.**
3. `SNIPER POOLS stage1_unique=2` — GeckoTerminal polling was finding only two new, supported SOL pools meeting stage-one conditions, with a 180s refresh. Cache default is now 60s (five pages/minute), with more informative rejection counts.
4. `verified_dex_selected=17` — pools with verified routes were kept in recheck rotation even after they were too old. Expired age pools are now retired from the active list with a bounded retry timeout (default 1800s). Tokens can be rediscovered later if they create a newer valid pool.

## Code changes

- Prioritizes fresh GeckoTerminal-poll pool hits ahead of broad FOMO/watchlist rotation and preserves reserved slots for pending candidates, verified live markets, and newly received launch hints.
- When a token has multiple fully supported SOL pairs, the bot prefers an age-eligible pool over a deep but expired one. All routing, SOL quote, minimum liquidity, verified momentum, price trend, indicative sellability, and reversal exit checks remain.
- Distinguishes `missing_pair_age` from an old token, keeping that candidate on short retry rather than a 30-minute age cooldown.
- Adds stage-one `SNIPER POOLS ... rejected={...}` diagnostics, and `FEED FALLBACK ... reason=missing_api_key`/HTTP502 status to separate upstream outage from configuration problems.
- Leaves standard `MIN_SCORE=68`, paper exploration `PAPER_EXPLORATION_MIN_SCORE=60`, and protective liquidity/volume thresholds unchanged. This version **does not force trades**.
- Removes sample state JSON and transient pytest cache from shipping ZIP. An existing Railway-mounted `STATE_FILE` must be retained across deployments.

## Railway environment (existing variables override new defaults)

```dotenv
PAPER_MODE=true
LIVE_TRADING_ENABLED=false
MIN_SCORE=68
PAPER_EXPLORATION_ENABLED=true
PAPER_EXPLORATION_MIN_SCORE=60
SNIPER_MAX_AGE_MINUTES=45
SNIPER_MIN_VOLUME_5M_USD=3000
QUALITY_POOL_CACHE_SECONDS=60
STALE_POOL_RECHECK_SECONDS=1800
FRESH_LAUNCH_FEED_ENABLED=true
# Optional but needed for PumpPortal real-time feed:
# PUMPPORTAL_API_KEY=(set privately in Railway Variables)
```

## How to tell it is working

Inspect `SNIPER POOLS` for `rejected={...}`, `cache_seconds=60`, and `stage1_unique=...`; examine `ENTRY SCAN` for how many verified and quality pools get rechecked, and watch `FILTER SUMMARY eligible` for nonzero entries. Even if `eligible>0`, an entry might still be blocked by score, price confirmation, insufficient cash, or indicative sellability checks. No market-data patch can guarantee candidates or profitable fills.

## Test status

Offline automated tests: `199 passed, 2 skipped` with `python -m pytest -q`. These are unit/regression tests; no Railway deployment or upstream WebSocket connection was tested. Do not enable live trading using this build.
