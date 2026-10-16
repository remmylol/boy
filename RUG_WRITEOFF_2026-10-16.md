# PAPER rug write-off upgrade — 2026-10-16

This update addresses logs such as:

```
ERROR PAPER EXIT UNAVAILABLE ... reason=primary_pool_quote_missing_fallback_valuation_only checks=120
```

## New behavior

The bot continues normal same-pool exit verification. If it receives successful,
fresh DexScreener pool responses showing the entry pool absent or drained to
<= $10 and finds no alternative supported SOL pool with viable estimated exit
depth, it counts corroborated checks. After **300 seconds** since the original
exit issue and **3** successful evidence checks on separate seconds, it records
`PAPER RUG WRITE-OFF`, including a zero-recovery 100% loss and explicit
`execution=paper_writeoff_no_sale`. This is a conservative PAPER write-off, not
proof that a sell happened or that recovery is permanently impossible.

`closed_trades` retains its accounting P&L and original issue evidence. The
mint enters a persisted `rugged_mints` blacklist, so ordinary reentry rotation
will not buy it again. The position no longer consumes an open slot; the bot
resumes only if this was the sole reason for its halt and the daily loss limit
has not been reached. No actual SOL is returned to the wallet or paper cash.

## Limitations

- Does **not** treat a rate limit, failed HTTP request, missing liquidity field,
  stale price alone, or high expected slippage as a confirmed rug.
- Positive GeckoTerminal reserves are indicative; if the original DEX pool
  remains unavailable for selling and no alternate liquid route is indexed,
  the prolonged observation can still result in conservative paper write-off.
- Supported alternative SOL liquidity prevents this auto write-off; the bot
  still requires separately verified sell execution before recording a sale.
- Once a mint is written off, an operator must edit the persisted state to
  remove it from `rugged_mints` before it can ever be reconsidered.
- These observations do not provide on-chain evidence of permanent rug removal.

## Config

```
PAPER_RUG_WRITEOFF_ENABLED=true
PAPER_RUG_WRITEOFF_AFTER_SECONDS=300
PAPER_RUG_WRITEOFF_MIN_CHECKS=3
PAPER_RUG_DUST_LIQUIDITY_USD=10
```

Ensure PAPER_MODE=true and LIVE_TRADING_ENABLED=false. Preserve your original
STATE_FILE on a persistent Railway volume. Review the log for `PAPER RUG WATCH`
and `PAPER RUG WRITE-OFF` and the JSON `closed_trades` entries.
