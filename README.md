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
