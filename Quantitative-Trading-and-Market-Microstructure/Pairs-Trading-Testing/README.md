# Pairs Trading Robustness Check

A cointegration-based statistical arbitrage strategy on S&P 500 equities, backtested net of transaction costs over five years — and then stress-tested against itself. Screening 124,750 candidate pairs makes false discoveries near-certain, so the strategy is re-evaluated using FDR control, the Deflated Sharpe Ratio, and bootstrap nulls, alongside a Kalman filter replacing the static hedge ratio.
