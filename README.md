# Solana Memecoin Bot — safe live-adapter staging package

## Important status

`bot.py` is still paper-trading only. `live_adapter.py` is a separately tested execution layer and is **not connected to the scanner/position manager**. Do not set `PAPER_MODE=false`; the bot intentionally refuses to start live until the adapter is integrated with live balance reconciliation and strategy state.

This staging version gives you:
- Read-only wallet/RPC validation (`python live_adapter.py --check-wallet`).
- A PumpPortal Local Transaction API adapter that locally signs transactions and submits them through your configured Solana RPC when explicitly called by reviewed code.
- Default-off live switch (`LIVE_TRADING_ENABLED=false`), buy cap, slippage/priority-fee caps, signer/fee-payer validation, preflight enabled, confirmation polling, and no automatic retry after ambiguous sends.
- Unit tests for safety gates. Tests do not contact mainnet and do not send transactions.

## Keep secrets private

Never put a private key, seed phrase, RPC provider URL containing an API token, or wallet export in GitHub. Add secrets only as Railway Variables. Use a dedicated hot wallet with only funds you can afford to lose. Do not share secrets with ChatGPT.

Railway Variables to configure later:
- `BOT_PRIVATE_KEY`: base58-encoded private key for the dedicated bot wallet (not the seed phrase).
- `SOLANA_RPC_URL`: HTTPS Solana mainnet RPC endpoint. A private RPC provider is preferable to the public endpoint for reliability; protect its URL as a secret if it contains an API key.
- Keep `LIVE_TRADING_ENABLED=false` until the live adapter is integrated and reviewed.

Non-secret conservative defaults in `.env.example`:
- `MAX_BUY_SOL=0.15`
- `LIVE_SLIPPAGE_PCT=3.0` (PumpPortal's API expects a percentage, not basis points)
- `LIVE_PRIORITY_FEE_SOL=0.00005`

## Test locally or in a safe build environment

Install dependencies, then run:

```bash
python -m pytest -q
python -m py_compile bot.py live_adapter.py
```

The tests are offline/unit tests. A successful test run does **not** mean a live trade was simulated or validated.

## Read-only wallet check

After setting `BOT_PRIVATE_KEY` and `SOLANA_RPC_URL` in Railway Variables, a one-off Railway command can run:

```bash
python live_adapter.py --check-wallet
```

It prints the wallet public address and SOL balance only; it sends no transaction. Verify the public address matches your dedicated wallet before any next step.

## Live execution integration is a separate required phase

Do not connect this adapter to automatic entries yet. Before enabling automated trading, integrate and test all of the following together:
1. SOL/USD conversion and sizing in SOL after reserving fees.
2. Confirmed token balance deltas on buys and actual token-unit accounting.
3. Reconcile holdings after Railway restarts; persistent state/volume is required.
4. Confirm actual wallet balance and exact mint token account before sells.
5. Ensure sell percentage applies only to this bot's token balance and that no other funds/tokens are kept in the bot wallet.
6. Idempotency and recovery for a timeout after send (never blindly repeat an uncertain order).
7. Live exit behavior under stale quotes, RPC failures, and insufficient liquidity.
8. Paper/live mode mutual exclusion and a kill switch.

## Execution provider

The adapter uses PumpPortal's Local Transaction API (`https://pumpportal.fun/api/trade-local`), which returns a transaction for your code to sign and send via your own RPC. PumpPortal documents a 0.5% fee per Local API trade, excluding network and other venue fees. Actual slippage, token taxes/transfer restrictions, and liquidity can make losses much larger than the configured stop-loss.

Official docs:
- https://pumpportal.fun/local-trading-api/trading-api/
- https://pumpportal.fun/fees/
