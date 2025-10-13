Project_1_Investment_Analysis/README.md

# Investment Analysis for Equity Portfolio

This project analyzes the performance and risk–return characteristics of a small equity portfolio composed of large U.S. financial institutions — **JPMorgan Chase (JPM)**, **Morgan Stanley (MS)**, and **Bank of America (BAC)** — over the year 2024.  
It forms part of my *Independent Quant Finance Projects* series, showcasing data-driven financial analysis using Python.

---

## 📈 Objectives
- Retrieve and visualize market data for selected equities.  
- Compute **simple** and **log returns** to compare return measurement techniques.  
- Construct and evaluate a **portfolio of financial stocks**.  
- Analyze **cumulative returns, volatility, and correlation** between assets.  
- Provide clear, reproducible code for quantitative portfolio analysis.

---

## 🧠 Methodology
1. **Data Collection** – Historical price data is downloaded via the `yfinance` API.  
2. **Data Processing** – Cleaning and formatting with `pandas`.  
3. **Return Calculations** –  
   - *Simple Return:* \( r_t = \frac{P_t - P_{t-1}}{P_{t-1}} \)  
   - *Log Return:* \( r_t = \ln(\frac{P_t}{P_{t-1}}) \)  
4. **Portfolio Analysis** – Aggregated portfolio returns based on equal weights, comparison of cumulative growth, and basic risk metrics (standard deviation, covariance).  
5. **Visualization** – Time-series plots of prices and returns using `matplotlib` and `plotly` for interactive insights.

---

## 🧰 Tools and Libraries
- **Python 3.10+**
- `pandas`, `numpy` – data manipulation and numerical computation  
- `yfinance` – market data retrieval  
- `matplotlib`, `plotly` – data visualization  

---

## 📊 Key Insights
- Strong co-movement between major U.S. banks during 2024, highlighting systemic exposure.  
- Log and simple returns yield consistent performance trends with minor scale differences.  
- Diversification benefits are limited due to high correlation among financial sector equities.

---

## 🚀 How to Run
1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/quant-finance-projects.git
