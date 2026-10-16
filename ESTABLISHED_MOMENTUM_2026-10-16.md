# Established SOL market-cap momentum (paper only)

This build switches **the default** from the <=45 minute new-pool sniper to a
market-cap screened, positive multi-timeframe **paper momentum** strategy.
It keeps the paper rug-pull write-off, persistent state, daily risk halt,
reverse-exit check, stop/take profit, and pool-specific rechecks.

## Default screen

| Filter | Requirement |
|---|---|
| Network, quote | Solana, actual SOL-quoted base-token pool |
| DEX identifiers | PumpSwap/Pump.fun, Raydium, Orca, Meteora paper observation only |
| Market cap | $500,000-$50,000,000 (editable) |
| If marketCap missing | `fdv` *proxy* allowed by default, labelled as such |
| Pool age | at least 60 minutes, **no maximum** (`MOMENTUM_MAX_PAIR_AGE_HOURS=0`) |
| Liquidity | at least $20,000 in the observed SOL pool |
| Volume | >=$2,000 in 5m and >=$20,000 in 1h |
| 5m transactions | >=10 with buys/sells >=1.1 and >0 sells |
| 5m price change | >=+1.5%, <=+25% |
| 1h price change | >=+3% |
| 6h price change | >=+1% |
| 24h price change | >=0% |
| Buy | Fresh quote, momentum confirmation, same-pool sell-depth estimate, optional independent crosscheck |
| Paper exit | Existing reversal, take profit, stop-loss, 45-minute default time exit, rug write-off after confirmed drain |

All the change windows must be **present**. A multi-window positive return is
only a proxy for upward trend. It is not a 1h/6h candle or moving average
analysis and can still buy near tops or after a price reversal.

For older tokens, discovery now scans the first **three** GeckoTerminal Solana
trending-pools pages, rotates Solana token profiles/boosts and broader DEX
search queries; indexed markets are rechecked with DexScreener. There is no
age cutoff at 45 minutes. New-pool websocket and bonding-curve work are
bypassed in this strategy, so those will no longer dominate API capacity.

**Important limitation:** These broadened DEX entries are *only simulated*;
DexScreener and GeckoTerminal price/liquidity readings are indicative, **not
actual executable swap quotes** and not a token safety audit. Never enable
live money via this build. A real live swap engine would require a separate
quote, swap-instruction, signing, execution, and reconciliation implementation.

## Deploy on Railway

1. Back up your current `STATE_FILE` and reuse the **same persistent file
   path**; do not reset your trade history or rug-pull blacklist.
2. Deploy this ZIP. It defaults to `MOMENTUM_SWING_MODE=true`, which overrides
   an old `SNIPER_MODE=true` variable. To be explicit, set
   `MOMENTUM_SWING_MODE=true`, `SNIPER_MODE=false`.
3. Use `.env.established_momentum.example` to overwrite stale sniper variables
   (especially `MAX_HOLD_MINUTES`, `DISCOVERY_SEARCH_TERMS`, trend thresholds).
4. Keep `PAPER_MODE=true` and `LIVE_TRADING_ENABLED=false`. Watch the
   `ESTABLISHED MOMENTUM PAPER MODE` startup line and `FILTER SUMMARY`
   rejections. Check portfolio and loss accounting during paper testing.
5. To adjust the capitalization band, change `MOMENTUM_MARKET_CAP_MIN_USD`
   and `MOMENTUM_MARKET_CAP_MAX_USD`. `MOMENTUM_ALLOW_FDV_FALLBACK=false`
   will reject tokens without an actual `marketCap` field.

Rugged mints remain blacklisted for paper reentry. Daily-loss and manual
halts are not cleared by the strategy switch.
