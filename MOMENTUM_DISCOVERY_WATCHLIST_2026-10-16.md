# Established Momentum Discovery + Watchlist Refresh (2026-10-16)

## Why it was still not trading
The provided FILTER SUMMARY logs show 0 of 58-60 eligible candidates; many are below the $500k market-cap floor or lack recent volume. This is not proof that any qualifying token exists in the current discovery universe. Lowering safety requirements or fabricating trades is inappropriate.

## Changes
1. Adds two pages of GeckoTerminal's documented network `/pools?order=h24_volume_usd_desc` feed to 5 trending pages per cache refresh. With a momentum-mode 90-second minimum refresh interval, this averages **under 5 discovery requests per minute** against their approximately 10/min public limit, leaving some headroom for separate safety-check requests. Rate limiting and incomplete upstream coverage may still occur.
2. Uses GeckoTerminal's capitalization data, **only when supplied**, to discard obviously undersized markets before DexScreener lookups. Missing cap is allowed into discovery and must be verified at final entry.
3. Quality-pool priority favors positive 1h / 6h / 24h and 5m movement; no priority hint authorizes a trade.
4. Corrects watchlist behavior: a verified pool that fails a trend/volume/cap rule enters a timed rejection cooldown; refreshing its liquidity no longer wipes out that rejection. Confirmed requalification clears the cooldown. Verified-pool scans skip cooling mints and rotate through others.
5. Logs Gecko quality-pool shortlisting rejects by type for insight into discovery constraints.

## Safety
- Paper mode only. No stablecoin-quoted or arbitrary-route swaps have been newly enabled.
- Existing entry liquidity, market-cap, volume, price-change, trend, independent same-pool sellability checks, rug-pull write-offs, reversal exits, and stored trading state remain unchanged.
- No real market feed, profitability or live fills were tested in this offline unit-test run.

## Deployment
Use this zip with existing Railway variables unchanged. `MOMENTUM_TOP_POOL_PAGES=2` is the new default and may be added explicitly as a variable. Momentum mode also clamps `QUALITY_POOL_CACHE_SECONDS` to at least 90 seconds to avoid excessive public API calls. Keep `PAPER_MODE=true` and `MOMENTUM_SWING_MODE=true`. Keep the existing mounted `STATE_FILE`. Review QUALITY POOLS / ENTRY SCAN / FILTER SUMMARY logs after a few refreshes. It is normal to have `eligible=0` when markets fail the filters.
