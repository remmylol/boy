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
