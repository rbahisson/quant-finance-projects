# Time-Series Momentum Strategy Backtesting 

This project implements and evaluates a 1-month time-series momentum (TSMOM) trading strategy on a small universe of U.S. and international equities using historical daily price data from Yahoo Finance.

The strategy takes long-only positions: for each asset, it holds one share when the 1-month momentum signal is positive, and stays in cash otherwise. Portfolio performance is tracked using explicit cash and position accounting, and results are compared against a buy-and-hold benchmark consisting of one share of each asset held continuously.

Key Findings: 
- The momentum strategy exhibits significantly lower volatility and drawdowns compared to buy-and-hold.
- However, it underperforms in terms of absolute returns during a strong equity bull market.
- Results suggest that short-horizon time-series momentum acts primarily as a risk-management overlay, rather than a return-enhancing strategy in this setting.
