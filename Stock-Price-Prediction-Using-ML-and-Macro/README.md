# Project 3: Stock Price Prediction of Bank of America Using Machine Learning and Macroeconomic Indicators

This project builds and evaluates machine learning models to predict **Bank of America (BAC)** stock prices using both financial market data and macroeconomic indicators.  
It combines time series analysis, feature engineering, and supervised learning to assess predictive performance across multiple models.

---

## Workflow Overview

### 1. Data Collection
- Download daily closing prices for:
  - **Financial stocks:** BAC, JPM, MS, C, WFC  
  - **Market and macro indicators:** S&P 500 (SPY), VIX, 10-Year Treasury Yield (^TNX), USD Index (DX-Y.NYB), Crude Oil (CL=F), and Gold (GC=F).
- Source data via the `yfinance` API from 2002 to 2025.

### 2. Data Cleaning
- Handle missing values with forward-fill (`ffill`) to maintain time-series continuity.  
- Verify completeness and integrity of merged data.

### 3. Exploratory Analysis
- Compute and visualize **correlation matrices** to assess relationships between BAC and other variables.  
- Plot long-term trends across all financial institutions and macroeconomic indicators.

### 4. Feature Engineering
- Create lagged variables for BAC prices and selected predictors.  
- Calculate technical and statistical indicators to enrich feature space.  
- Normalize and prepare the dataset for model training.

### 5. Model Building
- Implement multiple regression-based ML models:
  - **Linear Regression**
  - **Ridge Regression**
  - **Lasso Regression**
  - **Elastic Net**
- Split data into training and testing sets to evaluate out-of-sample performance.

### 6. Model Evaluation
- Use standard metrics such as:
  - **Mean Squared Error (MSE)**
  - **R² Score**
- Compare predictive accuracy across all models and visualize predicted vs. actual prices.

### 7. Visualization
- Plot predicted BAC prices against real observations to illustrate model performance.  
- Display residual plots and error distributions for diagnostic analysis.
