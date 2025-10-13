# Investment Analysis for Equity Portfolio

This notebook provides a structured workflow for analyzing the performance and risk characteristics of an equity portfolio composed of major U.S. financial institutions. The analysis is implemented in Python and demonstrates practical steps in quantitative portfolio analytics.

---

## Workflow Overview

### 1. Download Market Data
- Retrieve daily closing prices for **JPMorgan Chase (JPM)**, **Morgan Stanley (MS)**, and **Bank of America (BAC)**.  
- Use the `yfinance` library to access data between January 2024 and January 2025.  
- Store and clean the data using `pandas` for subsequent analysis.

### 2. Visualize Price Series
- Plot the historical closing prices of all three equities.  
- Use both static (`matplotlib`) and interactive (`plotly`) visualizations to explore trends and co-movement.

### 3. Calculate Returns
- **Simple Returns:** \( r_t = \frac{P_t - P_{t-1}}{P_{t-1}} \)  
- **Log Returns:** \( r_t = \ln \left(\frac{P_t}{P_{t-1}}\right) \)  
- Compare both approaches to assess scale and compounding effects.

### 4. Analyze Return Distributions
- Compute key descriptive statistics (mean, standard deviation, skewness, kurtosis).  
- Plot histograms of returns to visualize distributional properties.

### 5. Examine Correlation Structure
- Calculate the correlation matrix of returns to identify dependencies between assets.  
- Visualize the results using a heatmap for clarity.

### 6. Construct Portfolio Returns
- Create an equally weighted portfolio composed of the three equities.  
- Compute daily portfolio returns as the average of individual asset returns.

### 7. Evaluate Portfolio Performance
- Derive key performance metrics such as cumulative return and annualized volatility.  
- Compare individual stock performance against the aggregated portfolio.

### 8. Visualize Portfolio Dynamics
- Plot cumulative returns for both individual assets and the portfolio.  
- Highlight the diversification (or lack thereof) among correlated financial sector stocks.

### 9. Summarize Findings
- Financial sector equities exhibit strong co-movement and limited diversification.  
- Log and simple returns produce consistent results, with log returns preferred for compounded analysis.  
- The equally weighted portfolio provides stable but sector-concentrated exposure.
