## DEX momentum sniper — October 2026

This edition uses **DEX-only, confirmed-momentum paper entries**. It continues
observing new Pump.fun launches and collecting read-only trades through Solana RPC,
but it **does not place bonding-curve paper entries or live orders**.

Copy the values in `.env.sniper.example` into your Railway service variables.
Sniper parameters have their own names so older `MAX_PAIR_AGE_HOURS` and
`MOMENTUM_*` Railway variables cannot silently override the requested strategy.

- Pool age: **1–30 minutes** by default (1-minute minimum is a conservative
  confirmation delay). No pool older than 30 minutes can qualify.
- Verified, freshly quoted supported SOL pair, **at least $5,000 DEX liquidity**.
- Last 5 minutes: **$5,000+ volume**, buys/sells **1.3×+**, **+5% or more**
  price change. By default also requires at least 12 recent transactions;
  extremely high spikes and other pre-existing protections still apply.
- **2% maximum *estimated* buy impact** on the configured $10 position,
  assuming half of USD pool liquidity represents quote-side depth. This is
  **not an executable swap quote** and will not account precisely for fees,
  MEV, or changing liquidity. Paper P&L remains estimated only.
- **$10** paper positions, **+20%** take profit, **−35%** stop loss,
  **5-minute** maximum holding period; existing 5-second position monitoring.
- GeckoTerminal `trending_pools` and `new_pools` hints are prefiltered by
  creation time, 5-minute volume, and price increase. DexScreener independently
  rechecks all entries. Existing rotating verified DEX-pool watchlist is kept.

**Important:** If an upstream source omits pool creation time or five-minute
momentum, that pool is not promoted by the quality-pool feed. It may still be
found by other sources, but every entry must pass the independent live scan.
No eligible coins or no paper trades can still be the correct outcome. Paper
returns do not prove live fill profitability.

# Solana execution bridge — preview-only build

This package adds `live_execution.py`, a fail-closed bridge that checks a proposed purchase against the existing `live_safety.py` policy and unresolved entries in `order_journal.py`. The strategy imports the bridge at startup, so deployment catches missing-module errors. **The scanner does not submit orders.** `execute_buy` and `execute_sell` explicitly refuse all transactions. No signer is loaded by the bridge. `preview_buy` is an offline validation helper; its SOL/USD input must be independently obtained and timestamped.

## Railway
Upload the contents of this folder to the root of the GitHub repository, including `live_execution.py`. Keep:

```
PAPER_MODE=true
LIVE_TRADING_ENABLED=false
POSITION_SIZE_USD=10
MAX_POSITIONS=2
STATE_FILE=/data/bot_state_36.json
```

Retain your `/data` volume. Do not put private keys in GitHub or this ZIP. Restart the service and check that paper trading continues. Run `pytest -q` locally or in CI. **Do not set `LIVE_TRADING_ENABLED=true`: bot.py intentionally refuses startup.**

## Remaining blockers before a supervised real trade

1. Validate transaction instructions and fee/spend limits before signing; enforce a hard $10 *actual* USD cap.
2. Durably persist signed transaction bytes/signature before RPC broadcast; on restart reconcile on-chain status before retrying.
3. Reconcile actual token account balance, SOL spent, fees and token decimals after buy.
4. Implement a restricted sell for only the bot's tracked tokens, with quote checks and verified proceeds.
5. Test uncertain RPC responses, restarts, slippage, failed swaps, and one supervised small transaction. Keep unattended execution disabled.

This is an incremental wiring/test build, **not a live-trading release**.

### Discovery refresh / diagnostic update

The scanner now combines DexScreener profile and boost feeds with rotating public
DexScreener search queries. `DISCOVERY_SEARCH_TERMS` defaults to
`pump,solana,meme,cat,dog`; `DISCOVERY_SEARCHES_PER_SCAN` defaults to `2`;
`DISCOVERY_CACHE_SECONDS` defaults to `30`. Search is a supplemental discovery
source, **not** an execution or safety guarantee. SOL quote, PumpPortal route,
and the $10,000 minimum SOL-pair liquidity floor remain enforced. The bot logs
`DISCOVERY` counts and `FILTER SUMMARY` with reasons candidates failed.
Search results can include stale or irrelevant tokens; public API limits apply.

Keep `PAPER_MODE=true` and `LIVE_TRADING_ENABLED=false`.


## DexScreener rate-limit protection (paper mode)

The 5-second main loop is retained for **open-position** monitoring, while entry discovery and token-batch scanning are throttled. Recommended Railway variables:

```env
SCAN_INTERVAL_SECONDS=5
ENTRY_SCAN_INTERVAL_SECONDS=60
DISCOVERY_CACHE_SECONDS=60
MAX_ENTRY_TOKENS_PER_SCAN=60
ENTRY_BATCH_SIZE=30
MARKET_REQUEST_SPACING_SECONDS=1.5
RATE_LIMIT_COOLDOWN_SECONDS=120
PAPER_MODE=true
LIVE_TRADING_ENABLED=false
```

A DexScreener HTTP 429 starts a global cooldown (including discovery and held-position price queries). Open positions are **not** closed at stale prices. If the market price remains unavailable longer than `MAX_STALE_PRICE_SECONDS`, new entries are halted and manual review is needed. A five-minute hold limit is not guaranteed during API outages. The 60-token entry scan uses a rotating cursor, so it eventually considers tokens beyond the first 60.

### Discovery quality update
Search discovery now ignores unrelated USDC/non-SOL pairs, unsupported DEX routes,
and SOL itself; it deduplicates token mints and prioritizes supported pools
with at least $10,000 liquidity for up to half of the entry scan. Remaining
slots rotate across other discovered mints. Profiles/boosts still supply
backup discovery, so zero eligible tokens can remain normal. Default search
term is `pump` (override `DISCOVERY_SEARCH_TERMS` in Railway). Existing
rate-limit protection and five-second position checks remain unchanged.

### Continuous new-token discovery (paper mode)

The bot now subscribes to PumpPortal's public `subscribeNewToken` WebSocket
(`wss://pumpportal.fun/api/data`) in a background daemon thread. No wallet key
is required. Reconnects use bounded exponential backoff. Discovered mints are
held in an in-memory rolling pool and are **not** automatically tradeable: every
candidate must still pass DexScreener's supported SOL-pair, liquidity, age,
momentum, and risk filters. Newly created mints may not yet have indexed pairs.

Optional Railway environment variables:

- `FRESH_LAUNCH_FEED_ENABLED=true` (set false to disable the WebSocket feed)
- `FRESH_LAUNCH_TTL_SECONDS=3600` (discard mints older than one hour)
- `FRESH_LAUNCH_POOL_LIMIT=1500` (memory bound)
- `FRESH_LAUNCH_SCAN_QUOTA=40` (reserve up to 40 of 60 entry slots for fresh mints)

Watch `FRESH FEED connected`, `ENTRY SCAN ... fresh=... feed_connected=...`
and `DISCOVERY ... fresh_launch_feed=...`. The feed depends on PumpPortal
availability and is not a guarantee of qualifying candidates. The bot remains
paper-only; the websocket does not send trades or subscribe to wallet activity.

### Market-data diagnostics (October 2026)

`FILTER SUMMARY` now includes `market_data_rejections` to distinguish
`pair_not_indexed`, `no_sol_quoted_pair`, `unsupported_sol_route`,
`supported_pair_missing_price`, `supported_pair_liquidity_unavailable`, and
`supported_pair_low_liquidity`. A missing DexScreener liquidity field is **not**
proof that a pool has zero liquidity. The bot deliberately does **not** convert
Pump.fun bonding-curve reserves into conventional DEX USD liquidity; those are
not equivalent and doing so could bypass the entry safety filter. Paper mode
should remain enabled until independently verified executable pricing is added.

### Read-only Pump.fun bonding-curve diagnostics

The fresh-token scanner can now inspect on-chain Pump.fun bonding-curve
accounts using the already configured `SOLANA_RPC_URL`. No key or wallet signing
is required. Set `PUMP_CURVE_LOOKUP_ENABLED=true` and
`PUMP_CURVE_LOOKUPS_PER_SCAN=4` (default). `CURVE DATA` logs show real SOL
reserves, virtual SOL reserves, approximate curve market cap in SOL, and
whether a curve has graduated. `FILTER SUMMARY` reports `curve_checks` and
`curve_outcomes`. RPC errors are logged without exposing the RPC URL.

**Safety:** Virtual reserves are synthetic pricing reserves, not DEX pool
liquidity. Real SOL reserves are not equivalent to verified exit liquidity.
This integration does not use curve quotes to authorize paper entries or
estimate executable P&L. It deliberately keeps the existing liquidity,
price, momentum and supported-route requirements. Bonding-curve execution
modeling and verified trade-volume data are still needed before admitting
these tokens into the strategy. Live trading remains disabled.

### Bonding-curve quote groundwork (paper only)

`curve_paper.py` implements deterministic constant-product buy/sell **indicative**
quotes using actual on-chain virtual and real reserves. The scanner logs
`CURVE QUOTE` and `curve_quote_ready` when it can quote a 0.1 SOL buy.
This is *not* an executable quote: fee schedules, token-program behavior,
creator fees, network costs, and migration can change outcomes. It does not
turn a curve into an eligible entry. Verified SOL/USD, recent transaction flow,
reserve thresholds, and reliable recurring sell quotes are still required
before enabling curve positions. The existing DEX scanner and paper execution
are unchanged. Keep `PAPER_MODE=true` and `LIVE_TRADING_ENABLED=false`.


### Pump.fun trade-activity observation (paper-only staged rollout)

The optional `CURVE_ACTIVITY_ENABLED=true` opens a read-only PumpPortal
`subscribeTokenTrade` connection for a bounded rotating set of fresh launches.
`CURVE_ACTIVITY_MAX_SUBSCRIPTIONS=40` limits subscriptions;
`CURVE_ACTIVITY_MIN_TRADES=20` and `CURVE_ACTIVITY_MIN_VOLUME_SOL=2`
control the **diagnostic** `activity_ready` flag over a rolling 5-minute window.
`CURVE ACTIVITY` and `curve_activity_ready` appear in Railway logs.
This release does **not** open curve positions: actual paper entries require
verified SOL/USD conversion, fee-aware buy and exit quotes, real-reserve
constraints, and continuous position monitoring. Trade events and curve
quotes are indicative, not guaranteed fills. Keep `PAPER_MODE=true` and
`LIVE_TRADING_ENABLED=false`. The default stop loss is now 30%; explicit
Railway `STOP_LOSS_PCT` overrides that default.

### Immediate launch trade subscriptions and diagnostics

The trade observer now adds fresh mints to its bounded watchlist **when the
new-token event arrives**, rather than waiting for an entry scan. Subsequent
scans no longer reset that watchlist. It keeps at most
`CURVE_ACTIVITY_MAX_SUBSCRIPTIONS` mints (default 40), dropping the oldest
when full; subscriptions can still rotate quickly during heavy launch traffic.

Watch Railway logs for `CURVE ACTIVITY subscribed` and the
`curve_trade_diagnostics` field in `FILTER SUMMARY`, including `watched`,
`messages`, `valid_trades`, `subscription_batches`, and
`last_trade_age_seconds`. A WebSocket connection or a sent subscription
request is not proof that a particular token is producing trade events.
The observer remains diagnostic only: bonding-curve paper entries are still
blocked pending validated fees, executable exit estimates and monitoring.
Use `PAPER_MODE=true` and `LIVE_TRADING_ENABLED=false`.

### Current release: free read-only Solana RPC activity tracking

**This section supersedes the older paid PumpPortal trade-tracking notes above.**
The fresh-launch feed still uses PumpPortal's free `subscribeNewToken` stream,
but **the bot no longer opens or sends `subscribeTokenTrade`**. Instead it
polls the Pump.fun bonding-curve account's Solana transaction signatures via
`getSignaturesForAddress`, fetches a bounded number of `getTransaction` records,
and decodes verified Pump.fun Anchor `TradeEvent` self-CPI instructions (with
legacy `Program data` support). It excludes failed transactions, matches each
mint, avoids duplicate transaction signatures, and timestamps observed trades
using the on-chain block time. Historical polling may be incomplete for busy
markets or rotating mints; trade counts are **observed minimums**, not complete
volume figures. These RPC calls consume **your existing Helius API credits**,
so the data source needs no paid PumpPortal key but is still subject to Helius
free-tier rate limits and usage allowance.

Use the existing private `SOLANA_RPC_URL` Railway environment variable. Never
put its value or any API key into GitHub, logs, or a support chat. No new wallet,
secret, signing permission, or PumpPortal API key is needed.

Suggested Railway settings (low-throughput defaults):

```env
CURVE_ACTIVITY_ENABLED=true
CURVE_ACTIVITY_MAX_SUBSCRIPTIONS=40
RPC_TRADE_POLL_INTERVAL_SECONDS=30
RPC_TRADE_MINTS_PER_POLL=4
RPC_TRADE_SIGNATURE_LIMIT=12
RPC_TRADE_TRANSACTIONS_PER_POLL=5
CURVE_ACTIVITY_MIN_TRADES=20
POSITION_SIZE_USD=15
TAKE_PROFIT_PCT=0.20
STOP_LOSS_PCT=0.30
MAX_HOLD_MINUTES=5
PAPER_MODE=true
LIVE_TRADING_ENABLED=false
```

The RPC observer budgets at most **four mint signature queries plus five
transaction-detail queries per 30-second cycle** under the default settings;
that is an upper bound of roughly 18 RPC methods per minute **in this worker**
when enough launches and signatures are available. Existing price checks,
wallet balance monitoring, and bonding-curve lookups add further RPC calls.
HTTP 429 responses trigger a two-minute pause for the activity observer.
These settings prioritize predictable usage over exhaustive trade coverage.

**Expected Railway logs:**

```text
CURVE RPC ACTIVITY started (read-only Solana RPC; no paid trade subscription)
CURVE RPC ACTIVITY watched=40 polled=4 signature_scans=... tx_fetched=... valid_trades=... rpc_errors=... history_gaps=... pending=...
FILTER SUMMARY ... curve_activity_source=solana_rpc curve_trade_diagnostics={'source': 'solana_rpc', 'signature_scans': ..., 'tx_fetched': ..., 'valid_trades': ..., 'history_gaps': ..., 'rpc_errors': ...}
```

`valid_trades > 0` confirms that genuine Pump.fun events were decoded from
read-only RPC transactions. `history_gaps > 0` means a bounded signature query
could not cover all activity; the 5-minute aggregates may undercount. A zero
count alone does not prove the tracker is broken: the mint may have no recent
trades, no successful RPC transactions, or may rotate out between polls.

**Still blocked by design:** bonding-curve paper buy/sell entries. The current
TradeEvent prefix reports a quote-token amount, but modern Pump.fun tokens may
be SOL, USDC, or another token-quoted. Without an independently verified
quote mint we must not assume that amount represents SOL volume. The
`unverified_quote_amount_as_sol` activity metric is a nominal value **only if
SOL-quoted**, not verified SOL volume. `curve_activity_observed_threshold_met`
indicates that enough individual trade events were seen, but
`curve_activity_ready=0` stays conservative until quote-asset, fees, current
reserves and exit pricing are validated. It does **not** trigger curve entries.
The existing DEX-strategy paper positions and 5-second position monitoring
continue normally and independently. The currently configured DEX SOL-pair
liquidity floor is $5,000 unless increased in Railway settings.

### Free RPC activity tracker: transaction queue resilience

The RPC observer prioritizes newest signatures within its limited fetch allowance, drops stale pending work, and independently retries failed `getTransaction` calls up to three times with backoff. A failed signature no longer blocks other tokens' transaction retrieval. Diagnostics now include `tx_error_codes` (numeric RPC error codes only), `tx_retries`, `tx_dropped`, `tx_null`, `retry_waiting`, and `ignored_reasons`. These indicators are cumulative since startup and do **not** guarantee complete trade coverage. Numeric error codes intentionally avoid logging API keys or RPC URLs.

Use `FILTER SUMMARY ... curve_trade_diagnostics=...` to determine whether retrieval works. `tx_fetched > 0` with `valid_trades = 0` can mean the transaction didn't contain a recognized legacy Pump.fun TradeEvent, a quote token differs from SOL, or a transaction wasn't relevant to the curve. This release does not broaden trading-route support or enable bonding-curve paper orders. Keep `PAPER_MODE=true` and `LIVE_TRADING_ENABLED=false`.

### Version-1 RPC transactions and verified-DEX revisit slots

`curve_rpc_activity.py` requests `maxSupportedTransactionVersion=1` when reading
transactions through the existing read-only Solana RPC tracker. This targets
`getTransaction` RPC error `-32015` for version-1 transactions. The parser still
must recognize the emitted Pump.fun events; a successful fetch is not proof of
complete trade coverage. No signing or on-chain transactions were added.

Entry scanning now revisits previously **verified** Solana SOL-quoted
PumpPortal-compatible DEX pools, while continuing to rotate through new
Pump.fun launches and other discovery results. Every revisit makes a new
DexScreener lookup; cached pool eligibility is never treated as a valid price,
liquidity figure, momentum signal, or buy authorization. Pools that no longer
qualify are removed, and old entries expire.

Optional Railway settings (defaults shown):

```env
FRESH_LAUNCH_SCAN_QUOTA=24
VERIFIED_DEX_RECHECK_QUOTA=18
VERIFIED_DEX_TTL_SECONDS=900
MAX_ENTRY_TOKENS_PER_SCAN=60
PAPER_MODE=true
LIVE_TRADING_ENABLED=false
```

Look for `verified_dex_selected` and `verified_dex_watched` in `ENTRY SCAN`
logs, and `tx_error_codes` in `curve_trade_diagnostics`. The watchlist starts
empty after restart; it only fills after the bot observes valid eligible DEX
pools. `eligible=0` can still be correct when no current market meets the
existing route, liquidity and momentum requirements. Bonding-curve entries
remain disabled pending execution and exit validation.

### Verified-market retention and curve observation priority (October 2026)

A previously verified supported SOL DEX market now remains on the bounded
recheck list until its TTL expires if a later DexScreener response has no
indexed pair, missing price, or missing liquidity. **This does not permit
an entry from cached market data**: every new entry still requires current
price, liquidity, route and momentum checks. A confirmed unsupported route
or insufficient liquidity removes the mint from the verified list.

The read-only curve trade poller now prioritizes recently observed active
curves with at least `CURVE_MIN_REAL_SOL_FOR_OBSERVATION=1.0` real SOL reserve,
then observed trade count. This is an *observation-priority heuristic*, not
an entry liquidity threshold or proof of executable exit liquidity.
`FILTER SUMMARY` includes `curve_reserve_observation_ready`; individual
`CURVE ACTIVITY` records also display `reserve_observation_ready`.
Missing trade verification, excessive price impact, or zero real reserves
must not be bypassed to force simulation trades. Bonding-curve paper buys
remain disabled pending fee-aware, quote-unit-verified round-trip pricing.

The user's Railway environment settings `POSITION_SIZE_USD=10` and
`STOP_LOSS_PCT=0.35` are intentional; they remain unchanged by this update.

### Discovery rejection cooldowns (paper-only)

To avoid rescanning the same unsupported or unindexed token on every entry scan,
newly rejected mints are temporarily removed from entry-selection priority.
The rejection cooldown is **not** a permanent blacklist. Mints become eligible
for rechecking once it expires, and successfully verified DEX pools remain
subject to fresh pricing/liquidity and momentum validation before any buy.

```env
STRUCTURAL_REJECT_COOLDOWN_SECONDS=300
MISSING_DATA_COOLDOWN_SECONDS=120
```

`ENTRY SCAN` now reports `discovery_total` and `cooling_discovery`, and
`FILTER SUMMARY` reports `verified_market_this_scan`, `eligible_verified`,
`eligible_search`, and `cooling_total`. These numbers identify whether
sources are supplying actually verifiable markets rather than just token mints.

The existing free RPC tracker and disabled bonding-curve entries are unchanged.

### Quality-first liquid SOL pool discovery (additional source)

The bot now supplements DexScreener token profiles/boosts and the PumpPortal
new-token stream with **GeckoTerminal Solana trending pools and new pools**.
These free public endpoints are cached and can be rate-limited. They are only
used to select mint addresses for later validation. The bot does **not** trust
GeckoTerminal liquidity or price for its actual entry decision; the existing
DexScreener SOL-quoted PumpPortal route, $5,000 liquidity minimum, live price,
and momentum checks still apply. Only Pump.fun/PumpSwap routes are considered.

Optional Railway variables:

```env
QUALITY_POOL_DISCOVERY_ENABLED=true
QUALITY_POOL_CACHE_SECONDS=180
QUALITY_POOL_SCAN_QUOTA=18
QUALITY_POOL_MIN_VOLUME_1H_USD=10000
FRESH_LAUNCH_SCAN_QUOTA=24
PAPER_MODE=true
LIVE_TRADING_ENABLED=false
```

Look for `QUALITY POOLS discovered=... unique=... errors=...`, `DISCOVERY
sources=... quality_pools=...`, and `ENTRY SCAN ... quality_pool_selected=...
quality_pool_watched=...` in Railway. If the quality pool source returns zero
results, the bot continues using its prior discovery paths. Since the public
feed is limited to currently returned pools and only routes that this bot
supports, it may legitimately return no eligible tokens. This is not a
promise of additional trades or profits. Your configured position size and
stop-loss settings are left unchanged.

## Sniper-pool-first discovery (paper mode)

When `SNIPER_MODE=true`, GeckoTerminal's Solana `new_pools` pages (1 through
`SNIPER_NEW_POOL_PAGES`) and one trending-pools page are polled on the existing
`QUALITY_POOL_CACHE_SECONDS` cadence. New pools are prioritized ahead of generic
boosted tokens. Public GeckoTerminal results are cached and subject to rate
limits; they are *discovery hints*, not trade execution quotes.

Before a discovered pool receives a DEX scan slot, its reported metadata must
show a supported SOL-quoted Pump.fun/PumpSwap route, a valid price, at least
$5,000 liquidity, age 1–30 minutes, at least $5,000 five-minute trading volume,
+5% to +80% five-minute price movement, 12 five-minute transactions, and at
least 1.3 buys per sell (with nonzero sells). Missing or malformed metrics are
rejected, never treated as positive signals. These conditions are checked again
from fresh DexScreener market data before any paper trade.

Sniper entry scans consider qualified new/trending pools first, followed by
previously verified DEX pools and at most `SNIPER_LAUNCH_PROBE_QUOTA` raw fresh
launches. Generic DexScreener profile/boost addresses no longer fill remaining
sniper scan slots. Fewer than 60 evaluated tokens is expected when few pools
qualify; that is preferable to scanning untradeable pools.

Suggested Railway configuration:

```
SNIPER_MODE=true
SNIPER_NEW_POOL_PAGES=3
SNIPER_LAUNCH_PROBE_QUOTA=6
SNIPER_VERIFIED_RECHECK_QUOTA=12
QUALITY_POOL_CACHE_SECONDS=180
PAPER_MODE=true
LIVE_TRADING_ENABLED=false
```

Look for `SNIPER POOLS discovered=... qualified_unique=...` and `ENTRY SCAN
... quality_pool_selected=...`. A zero-qualified-pool refresh is possible and
not evidence that the bot has stopped. Positions still use the five-second
monitor, and bonding-curve paper entries remain disabled.

## Two-stage sniper discovery (paper-only)

**Stage 1: discover and watch.** The sniper polls up to five pages of GeckoTerminal's
Solana newly-created pools plus trending pools, and keeps pools with a supported
SOL quote, supported DEX route, recorded creation time within 1–30 minutes,
valid price, and at least $5,000 reported liquidity. **No volume, buy ratio, or
price-rise requirement is applied yet.** This prevents promising pools from
being discarded before momentum begins. The existing free PumpPortal new-token
stream remains a separate launch-discovery source; its mints are probed and
rechecked for DEX migration. GeckoTerminal discovery data is not trusted as a fill quote.

**Stage 2: recheck and confirm.** An expiring, bounded watchlist is rotated each
entry scan, including pools without immediate momentum. Every potential buy
must be freshly verified using DexScreener's supported SOL pair, at least $5,000
DEX liquidity, 5-minute volume >= $5,000, at least +5% 5-minute change, at
least 1.3x buys/sells, minimum 12 trades, acceptable entry-impact estimate,
and the existing score and execution safeguards. Pools older than 30 minutes
are removed from the watchlist after verification. Bonds remain diagnostics-only.

Railway overrides (optional; defaults shown):

```env
SNIPER_MODE=true
SNIPER_NEW_POOL_PAGES=4
SNIPER_WATCHLIST_LIMIT=250
SNIPER_WATCHLIST_RECHECK_QUOTA=36
SNIPER_WATCHLIST_TTL_SECONDS=1800
SNIPER_LAUNCH_PROBE_QUOTA=6
QUALITY_POOL_CACHE_SECONDS=180
PAPER_MODE=true
LIVE_TRADING_ENABLED=false
```

Check `SNIPER POOLS stage1_discovered=... stage1_unique=...` and
`SNIPER STAGES watchlist=... checked=...` alongside the ordinary
`FILTER SUMMARY eligible=...`. A nonzero watchlist does **not** imply the pools
currently satisfy the stricter buying rules. The public sources may be delayed,
rate-limited, or return zero eligible pools; trades are never guaranteed.

### Paper position with unavailable exit liquidity (October 2026 fix)

When a held paper position has no valid price, DEX liquidity, or an acceptable estimated exit, it **remains open and unresolved**. The bot records `exit_issues[mint]` in the existing persistent state file with `status=EXIT_UNAVAILABLE`, first/last observed timestamps, and retry count. It logs `PAPER EXIT UNAVAILABLE` at most once per token per 60 seconds by default, while retrying quotes on every normal position-management cycle. No sale or realized P&L is invented. New entries stay halted until operator review, **including after quote recovery**. Do not delete the saved state or remove the position solely to clear the error. Set `PAPER_EXIT_WARNING_INTERVAL_SECONDS=60` in Railway (minimum 30) to adjust warning frequency. This release changes logging/status only; it does not guarantee exits or add an independently verified second liquidity provider.

### Pool-pinned exits and safer sniper discovery

New paper positions record their exact `pairAddress` / DEX at entry. Held-position
pricing uses only that pool and will **never** select another token pool to
manufacture a successful paper exit. If DexScreener cannot verify that pool,
the scanner may inspect the exact GeckoTerminal Solana pool for an indicative
price and reserve reading, cross-checking the base mint. Results are cached
briefly (`PAPER_POOL_FALLBACK_SECONDS=30`); no live transaction is signed.
A GeckoTerminal reserve/price is an *estimated paper mark*, **not** an
executable sell quote or proof of liquidity. If both sources fail, the bot
retains the unresolved position, halts new entries, and throttles warnings.
Existing state positions created before this release may lack a pinned pool;
these retain the old conservative behavior and should not be automatically
converted or deleted.

The sniper now inspects 5 new-pool pages and 2 trending-pool pages per public
GeckoTerminal refresh (adjust `SNIPER_NEW_POOL_PAGES` and
`SNIPER_TRENDING_POOL_PAGES`). Final entry filters are unchanged except for an
extra **1.5x minimum SOL-pair liquidity cushion**
(`SNIPER_MIN_ENTRY_LIQUIDITY_MULTIPLIER=1.5`, i.e. $7,500 on a $5,000 floor)
to reduce fragile pool entries. This may reduce entries while favoring more
viable pools. Paper-only: `PAPER_MODE=true`, `LIVE_TRADING_ENABLED=false`.
