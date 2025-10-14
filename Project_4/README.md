# Project 4 - Volatility Modeling Using Quantitative Models

This project demonstrates how to model and forecast financial market volatility using three quantitative approaches — *ARCH*, *GARCH*, and *EWMA* — applied to *JPMorgan Chase (JPM)* daily returns.  
It highlights volatility clustering, persistence, and conditional heteroskedasticity in financial time series.

---

## Workflow Overview

### 1. Data Collection
- Retrieve daily historical price data for *JPMorgan Chase (JPM)*.  
- Data is downloaded using both:
  - The Alpha Vantage API (requires API key)  
  - The Yahoo Finance (`yfinance`) library.  
- Compute daily percentage returns from adjusted closing prices.

### 2. ARCH Model
- Specify an *ARCH(1)* model using the `arch` package.  
- Fit the model to daily returns and extract conditional volatility estimates.  
- Forecast short-term volatility (5-day horizon).  
- Analyze volatility clustering effects in residuals.

### 3. GARCH Model
- Implement a *GARCH(1,1)* model to capture both short- and long-term volatility persistence.  
- Estimate parameters via maximum likelihood.  
- Evaluate model adequacy using summary statistics and diagnostic plots.  
- Generate multi-step ahead volatility forecasts.

### 4. EWMA Model
- Apply *Exponentially Weighted Moving Average (EWMA)* to model time-varying volatility.  
- Assign exponentially decaying weights to past squared returns.  
- Compare dynamic volatility paths with ARCH/GARCH models.

### 5. Model Comparison
- Plot and compare conditional volatility estimates from all three models.  
- Interpret persistence, mean reversion, and forecast smoothness.  
- Discuss implications for *risk management*, *VaR estimation*, and *option pricing*.
