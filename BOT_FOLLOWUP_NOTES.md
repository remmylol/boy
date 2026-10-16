# 2026-10-16: feed failure and paper exploration follow-up

## Cause of observed no-trades
- New token WebSocket replied HTTP 502 from upstream nginx. This is not fixable by lowering trade filters. Logging is now brief and sanitized; on upstream 502/503/504, retries slow to 60s. The configured optional `PUMPPORTAL_API_KEY` is used with the official `?api-key=` WebSocket parameter. Never commit an API key. The stream may still remain unavailable.
- GeckoTerminal new-pool polling is retained as a **discovery fallback**, with fresh DexScreener verification for all potential entries. It is *not* equivalent to the real-time new-token feed, and zero curve trades watched is expected without fresh mints.
- The logs' repeated eligible token scored ~62, below the main 68 threshold. A distinct **paper exploration** cohort can test 60-67.9 without changing the main strategy or promoting simulated success to a real fill.

## New settings (Railway Variables override defaults)
```env
PAPER_MODE=true
LIVE_TRADING_ENABLED=false
MIN_SCORE=68
PAPER_EXPLORATION_ENABLED=true
PAPER_EXPLORATION_MIN_SCORE=60
PAPER_EXPLORATION_DAILY_LIMIT=2
PAPER_EXPLORATION_POSITION_SIZE_USD=5
# Optional API key for documented PumpPortal WebSocket URL, never log it:
# PUMPPORTAL_API_KEY=...
```

Exploration only runs in paper mode, maximum two fills per calendar day, $5 each (or less if available cash), one concurrent experimental paper position. Regular age, route, verified SOL-pair liquidity, momentum, second-price-confirmation, independent-pool and indicative same-pool sell checks remain unchanged. Immediate reversal exits remain enabled. A high score is not a guarantee of safety, and indicative paper liquidity is not a firm execution quote.

## Check the logs
`FRESH FEED unavailable ... HTTP502` and `FEED FALLBACK mode=polling_geckoterminal_new_pools` distinguish stream outage from discovery complete outage. `PAPER EXPLORATION SCREEN`, `PAPER ENTRY SKIP ... entry_short_trend`, `PAPER EXPLORATION BUY`, and `PAPER ENTRY DECISIONS` explain decisions. The stream's 502 may persist until the provider recovers.

## Offline tests
`python -m unittest test_feed_exploration_followup test_pending_entry_upgrade test_reversal_shadow_upgrade -q`
