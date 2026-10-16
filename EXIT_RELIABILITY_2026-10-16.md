# Paper-only exit reliability update

## Root issue
Froggie showed liquidity at entry, then original-pool data became unavailable. Its remaining pool value was only indicative from GeckoTerminal; a real swap exit was not proven.

## Added safeguards
* **Independent source at entry:** After the original DexScreener pool recheck and indicative same-pool exit-impact test, compare the identical Solana pool on GeckoTerminal. Reject entries if source is unavailable, if liquidity is <70% of DexScreener's reported USD liquidity or below $5,000, or if prices differ by >12%. This is not an executable quote and cannot guarantee sellability. The cross-check only runs on actual candidates; failures halt that individual entry, not monitoring of held positions.
* **No fallback-only estimated exits:** GeckoTerminal fallback is permitted for read-only portfolio observations, but when `PAPER_EXIT_REQUIRE_PRIMARY_QUOTE=true`, it will not produce a completed paper SELL, realized P&L, or recorded TP success. Position stays open and new entries halt pending operator review.
* **Specific exit problems:** Separates missing price, missing liquidity, excessive modeled exit impact, and fallback-only prices. Records fallback-only and unverified-exit observation counters per open trade.
* **Throttled warnings:** Per-token pool fallback warnings at most once per 60 seconds; unresolved exit warnings are already throttled.

## Tradeoffs
This deliberately decreases paper buy count and may cause extra safety halts during temporary market-data outages. GeckoTerminal/DexScreener can disagree due to latency or different calculations; two-source agreement is **not** proof of an executable sale. No real-money trading enabled.

## Deployment
Railway Variables take precedence over defaults and the included example. Preserve `PAPER_MODE=true` and `LIVE_TRADING_ENABLED=false`. Do not restart or wipe state to hide an unresolved position. FOMO endpoints may charge for refresh after restarting the process. 
