# Paper bot: market-data productivity / queue control update

This build starts from `boy_fomo_smart_reentry_5min_secondary_liquidity.zip` and preserves paper-only entry limits, five-minute reversal reentry cooldown, route checks, verified SOL-pair depth, two-price confirmation, independent prebuy sellability, and immediate-reversal exits.

## What changed

1. **Spend fewer external liquidity calls on obvious rejects.** Before a GeckoTerminal pool verification, the candidate must already meet liquidity-independent age, SOL-route, quote, 5-minute volume, trade-count, buy/sell, and momentum conditions. This is only a scheduling filter: it cannot approve a buy.
2. **Priority-sorted follow-up.** Missing-liquidity pools with stronger observed trade activity are checked first (within each market-data batch). Strong candidates that run into the per-scan or per-minute request cap are placed in a bounded, expiring, deduplicated retry queue. Due mints return to the entry scanner and must be verified from fresh primary market data. Negative depth results are cached longer to avoid hammering the same pool. Confirmed low primary liquidity is **never** overridden.
3. **Safe cache on upstream 429.** A recently verified GeckoTerminal pool can still be used until its strict cache expiry when the upstream endpoint returns 429; the current DexScreener price must still agree. A cached failure never permits an entry. No verification is extended beyond its expiry.
4. **RPC trade observer queue pressure.** The read-only curve event tracker now polls fewer mint-address signature pages per cycle, rotates across the candidate set, drops expired work, and pauses new signature ingestion at 75% pending queue capacity until more `getTransaction` work has drained. It reports backlog and coverage-gap counters. Default read-only transaction work increases from 5 to 8 per poll. Trades potentially missed while backpressured remain unknown; they are **not** counted as zero activity for any buy authorization.
5. **Opportunity funnel and reentry diagnostics.** A `OPPORTUNITY FUNNEL` line separates DEX-eligible candidates, missing liquidity, unsupported routes, quote-only curves, disabled curve execution, remaining verification queue, and RPC coverage gaps. `PAPER REENTRY DUE` identifies eligible-for-rescreening previously sold mints.

## Suggested Railway variables (optional defaults shown)

```
PAPER_MODE=true
LIVE_TRADING_ENABLED=false
MIN_SCORE=68
PAPER_REVERSAL_REENTRY_COOLDOWN_SECONDS=300
PAPER_REENTRY_COOLDOWN_SECONDS=180
PAPER_SECONDARY_LIQUIDITY_ENABLED=true
PAPER_SECONDARY_LIQUIDITY_MAX_PER_MINUTE=4
PAPER_SECONDARY_LIQUIDITY_PER_SCAN=2
PAPER_SECONDARY_DEFERRED_QUOTA=2
PAPER_SECONDARY_DEFERRED_TTL_SECONDS=360
RPC_TRADE_TRANSACTIONS_PER_POLL=8
RPC_TRADE_MAX_PENDING=160
```

Do **not** raise request rates indiscriminately: the external endpoints have provider-specific constraints. If Railway already has variables defined, they override the defaults in the packaged source. Ensure `STATE_FILE` points to a persistent Railway volume to preserve closed trades, cooldown histories, and paper equity across redeploys.

## How to verify after deployment

- `OPPORTUNITY FUNNEL ... secondary_waiting=` will reveal deferred checks waiting on a budget or cooldown.
- `LIQUIDITY SECONDARY ... queued_for_scan_budget / queued_for_budget` means a candidate was deferred, *not* approved.
- `curve_trade_diagnostics` now includes `backpressure_cycles`, `signature_scans_deferred`, `pending_peak`, `rpc_gap_signatures`, `rpc_gap_overflow`, and `queue_overflow_drops`. High values indicate incomplete on-chain trade coverage. Curve-only execution stays disabled.
- `PAPER REENTRY DUE` is a watch signal, not a buy. All checks remain necessary.

## Testing limits

`pytest -q` passes with deterministic offline fixtures; no live Solana swaps, real funds, paid subscriptions, or Railway APIs were used in testing. Paper P&L estimates can deviate materially from executable fills.
