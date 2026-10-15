# Solana bot — safe live-adapter staging package

This combines the latest $36 paper bot and the previous standalone PumpPortal live adapter, **without wiring automatic execution**. The strategy refuses to start if `PAPER_MODE=false` OR `LIVE_TRADING_ENABLED=true`. The standalone adapter also refuses trades unless explicitly enabled; **do not enable it in this release**. No private key is required to deploy or monitor the wallet.

## Railway / GitHub
1. Back up the repository and paper state. Upload `bot.py`, `live_adapter.py`, `requirements.txt`, and `.env.example` (never upload `.env` or secrets).
2. Railway variables: `PAPER_MODE=true`, `LIVE_TRADING_ENABLED=false`, `STARTING_CAPITAL_USD=36`, `POSITION_SIZE_USD=10`, `MAX_POSITIONS=2`, `STATE_FILE=bot_state_36.json`, plus your public `SOLANA_WALLET_ADDRESS` and private Helius `SOLANA_RPC_URL`. Do not add `BOT_PRIVATE_KEY` for this phase.
3. Ensure start command is `python bot.py`. Redeploy and check logs. If a persisted state exists, its cash/positions override starting capital.
4. Run `python -m pytest -q` and `python -m py_compile bot.py live_adapter.py` in a local/test environment.
5. Monitor paper buys/sells and wallet readings for 24–48 hours; verify no duplicate buys, stale quotes, or exceptions.

## Remaining blockers to automated live trading
The standalone adapter is NOT safe to attach to automatic entry/exit signals yet. It needs USD→SOL sizing with fee reserve, verified mint/ATA token deltas, partial fill and sellability handling, confirmed transaction reconciliation, idempotent restart recovery after ambiguous RPC timeouts, persistent Railway volume, error-triggered kill switch, and tests with mocked RPC and an explicitly supervised small mainnet buy/sell. $10 is the **paper** trade size in this package, not an enforced live USD order limit. `MAX_BUY_SOL` is a SOL cap, not a USD cap. Never use this package to send real trades.

## Safety review update (2026-10-15)

This package includes `live_safety.py`, a **tested read-only USD purchase preflight**:
- Maximum purchase: $10 USD, converted to SOL using a validated fresh SOL/USD price.
- At most two open positions; refuse purchases when any order is pending or uncertain.
- Require verified wallet data and reserve at least $5 USD equivalent in SOL.
- Reject missing, invalid, or stale price data.

**Crucial:** These are isolated preflight checks, **not yet connected to live_adapter.execute_trade**. The strategy remains paper-only and refuses to start in live mode. Do NOT turn on live trading by changing environment variables. The adapter's existing `MAX_BUY_SOL` cap is SOL-denominated, NOT a $10 limit. The current code does not have persistent order reconciliation, verified token receipt/sellability, or a safe automatic sell path. Until those are implemented and independently tested, this is a staging package, not an unattended live bot.

Railway: deploy the contents to the GitHub branch used by Railway, keep `PAPER_MODE=true` and `LIVE_TRADING_ENABLED=false`, set `STARTING_CAPITAL_USD=36`, `POSITION_SIZE_USD=10`, `MAX_POSITIONS=2`, and configure `SOLANA_WALLET_ADDRESS` and `SOLANA_RPC_URL` as private Railway variables (never commit keys). Set `STATE_FILE=/data/bot_state_36.json` only after mounting a persistent Railway volume at `/data`; otherwise leave the default and expect paper state to reset on redeploy. Run `python -m pytest -q` locally or in CI. No real trade should be attempted from this package.
