# Paper smart reentry and missing-liquidity verification

This release builds on `boy_fomo_fresh_pool_stale_rotation_fix.zip` without resetting the persisted bot portfolio.

## Reentry behavior

- The old `seen_tokens` permanent ban is replaced by a decision based on **persisted `closed_trades`**, not symbols. Mint identities are compared, not tickers.
- After an **immediate reversal**, the same mint becomes eligible again after **300 seconds (5 minutes)**. Other normal exits use **180 seconds (3 minutes)**. Exits involving impairment or liquidity deterioration wait at least **3600 seconds (1 hour)** and must requalify. Unresolved exit issues stay blocked.
- A reentry must pass all normal route, liquidity, volume, buy/sell, change, score, paper sellability and position checks. An independent second upward price observation is mandatory even when the ordinary entry-confirmation feature is turned off.
- Old price observations are wiped when the prior position closes. A closed mint gets a reserved scan slot after its cooldown even if an older, unrelated scanner rejection is still cooling down; it is NOT automatically bought, and the new pool must pass all fresh checks.
- A previously traded mint can be reconsidered with a pool age up to **180 minutes** (configurable, maximum 360), compared with the normal 45-minute sniper age gate. Momentum and everything else are unchanged.
- Maximum **two completed paper reentries per mint per rolling hour**; new reentries are blocked if that mint has realized **$2 or more in paper losses** during that hour. It can only hold one position per mint.
- Exit history is persisted in the normal `STATE_FILE`, including reentry metadata, so restarts cannot clear the limits. Legacy `seen_tokens` without matching closed-trade history remain blocked for safety.

## Missing liquidity handling

- Applies **only to missing/`null`** DexScreener liquidity, never a reported value of `$0`, low liquidity, unsupported quote mint or unsupported DEX route.
- Secondary read-only GeckoTerminal call for **the exact same pool**. It checks pool ID, Solana base mint, wrapped-SOL quote mint, independent USD price (within the configured deviation) and **at least the normal safety depth, including the sniper buffer**.
- At most 2 lookup attempts per scan and 4 requests/minute, 45-second local cache; API HTTP 429 triggers a two-minute cooldown. Pool lookup failures fail closed.
- The primary DexScreener price is still required for an entry and for reversal/sell modeling. Missing depth can be supplemented by verified **indicative** secondary reserves in paper mode only. Independent liquidity data are not executable quotes or a guarantee of actual sellability.
- Paper pre-buy requires another same-pool check (usually from the short validated cache) and the existing paper exit impact estimate. No live trading is enabled.
- Logs include `LIQUIDITY SECONDARY`, `SECONDARY LIQUIDITY VERIFIED/UNVERIFIED`, and `PAPER REENTRY APPROVED` or an explicit cooldown/limit rejection.

## Suggested Railway environment variables

```dotenv
PAPER_MODE=true
LIVE_TRADING_ENABLED=false
PAPER_REENTRY_ENABLED=true
PAPER_REENTRY_COOLDOWN_SECONDS=180
PAPER_REVERSAL_REENTRY_COOLDOWN_SECONDS=300
PAPER_IMPAIRED_REENTRY_COOLDOWN_SECONDS=3600
PAPER_REENTRY_LOOKBACK_SECONDS=3600
PAPER_REENTRY_MAX_PER_WINDOW=2
PAPER_REENTRY_MAX_LOSS_USD=2
PAPER_REENTRY_MAX_POOL_AGE_MINUTES=180
PAPER_REENTRY_SCAN_QUOTA=4
PAPER_SECONDARY_LIQUIDITY_ENABLED=true
PAPER_SECONDARY_LIQUIDITY_MAX_PER_MINUTE=4
PAPER_SECONDARY_LIQUIDITY_PER_SCAN=2
PAPER_SECONDARY_LIQUIDITY_CACHE_SECONDS=45
ENTRY_TREND_CONFIRM_ENABLED=true
```

These are defaults already in the code. Railway variables explicitly defined in the service override them. Do not upload private keys or a real wallet key: this ZIP **simulates paper trades only**. `PUMPPORTAL_API_KEY` remains optional and will not fix upstream HTTP 502 responses.

Run offline tests with `python -m pytest -q` after installing dependencies from `requirements.txt` and `pytest`.
