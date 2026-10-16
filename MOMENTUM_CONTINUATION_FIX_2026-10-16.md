# Established-token momentum-continuation patch — October 16, 2026

## Why the paper portfolio made no trades

The observed 52–60 candidates per entry scan were rejected, mainly by the
strict $1k generic volume / $2k momentum 5m volume floor, positive 1.5% 5m
change requirement, market-cap ceiling and $20k SOL-pool liquidity minimum.
The 52-token repeated scans reflected a limited trending discovery set and
repeated verified-market watchlist. No bond-curve/WebSocket activity is
necessary for this strategy.

## New PAPER entry defaults

- Solana SOL-quoted supported DEX pools only; no new non-SOL swap route added.
- Market cap / FDV proxy (labeled): $500,000 to $250,000,000.
- Pool age: 60 minutes or older; no maximum age.
- Pool liquidity: $15,000 minimum; no fabricated zero-liquidity quote.
- Reported volume: >=$800 in 5 minutes, >=$12,000 in 1 hour.
- Recent price change: +0.2% to +18% in 5m; >=+2% in 1h;
  >=+0.5% in 6h; >=0% in 24h. Missing price windows fail closed.
- At least 8 transactions in 5m, buys/sells >=1.05, some actual sells,
  and five-minute volume/pool liquidity >=0.005.
- Standard paper entry score threshold: 62; re-checks and independent pool
  exit-depth checks still apply. Exploration remains size-/count-limited.
- GeckoTerminal trending discovery pages: 5; rank positive 1h/6h movers
  ahead of otherwise similar downtrending pools. Rotate verified/quality
  pool candidates across scans.

These are screening proxies, not evidence of profitability or an executable
trade. Greater eligibility does not guarantee any position will open.

## Important technical change

Established mode no longer inherits `MIN_VOLUME_5M_USD=1000` from the older
strategy. The swing-specific volume floor is now authoritative, and is
independent of the legacy generic volume floor. The continuation trend
checks remain mandatory even if FAST_MOMENTUM_ENABLED=false.

## Railway deployment

1. Back up the existing persistent state file and keep the exact same
   `STATE_FILE` path; do not clear rug-pull exclusions, closed trades, or
   other risk halts.
2. Deploy the revised ZIP, using the `boy-main` contents as in the previous
   deployment. Set `MOMENTUM_SWING_MODE=true`, `SNIPER_MODE=false`,
   `PAPER_MODE=true` and `LIVE_TRADING_ENABLED=false`.
3. Copy **all** values from `.env.momentum_continuation.example` into the
   existing Railway Variables. Previously configured Railway environment
   variables override new defaults in `bot.py`. In particular, update:
   `MIN_SCORE`, `MOMENTUM_MIN_VOLUME_5M_USD`, `MOMENTUM_MIN_VOLUME_1H_USD`,
   `MOMENTUM_MIN_CHANGE_5M_PCT`, `MOMENTUM_MARKET_CAP_MAX_USD`,
   `MOMENTUM_MIN_LIQUIDITY_USD`, and `MOMENTUM_TRENDING_POOL_PAGES`.
4. Watch `FILTER SUMMARY`, `PAPER ENTRY DECISIONS`, and `CANDIDATE` lines;
   if all are still rejected, check the actual Railway variable values first.

## Preserved risk features

Paper exit write-offs for confirmed persistent drained liquidity, same-pool
exit price/sellability checks, stop-loss, trailing stop option, immediate
reversal detection, maximum hold, daily-loss/manual halts, persistent state,
and the rug-pull reentry blacklist remain intact. Do not enable live trading:
these DEX market data and exit-depth reads are indicative, not verifiable
executed swap quotes.

## Verification

257 local unit/regression tests passed; 2 skipped. This is not a live-market
performance/backtest verification.
