# Paper entry recheck upgrade

Based on `boy_fomo_reversal_shadow_strategy_upgrade.zip` (latest Library ZIP retrieved).

- Paper-score default 68 (previously 70). Set `MIN_SCORE` explicitly in deployment variables to override; environment settings take precedence. No score relaxation in non-paper default.
- Entry-scan default 15 seconds, minimum 10 seconds, with 10-second trend observation minimum. API response time and Dex rate limits can lengthen actual observations.
- Pending-eligible tokens awaiting second price observation receive priority during subsequent entry scans (8 slots, 90-second TTL). Every recheck fetches fresh market data; stale scores/prices cannot trigger purchases.
- Fresh PumpPortal websocket subscription enabled by default; requires working network, installed `websocket-client`, and reachable service. Logs show enabled status and connection failures; an enabled setting does not guarantee connectivity.
- Extended logs show pending candidates and entry rejection breakdown.
- Existing safety checks, pool verification, exit sellability checks, and immediate reversal paper exit logic retained.
- In Railway, update any existing variables that override these defaults: `MIN_SCORE=68`, `FRESH_LAUNCH_FEED_ENABLED=true`, `ENTRY_SCAN_INTERVAL_SECONDS=15`, `ENTRY_TREND_MIN_OBSERVATION_SECONDS=10`.
- This does not guarantee trades or profitability. Paper-mode estimates are not actual executable fills; live trading remains disabled.

Run `python -m unittest test_pending_entry_upgrade test_reversal_shadow_upgrade test_two_stage_sniper test_fast_momentum -q` for focused offline tests. Full suite needs optional runtime dependencies.
