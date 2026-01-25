### **Project 10 - Total Portfolio Risk Analysis**

This project lets users build a custom options portfolio using live market data from Yahoo Finance, and analyze its risk profile in real time.  
The tool supports both **European** (Black-Scholes) and **American** (Binomial Tree) options, allowing you to input strike price, maturity, and quantity for multiple instruments.

It automatically fetches spot prices, dividend yields, and volatilities via `yfinance`, then computes:
- **Portfolio Value (PV)**
- **Greeks**: Delta, Gamma, Vega, Theta  
- **1-Day 95% Value-at-Risk (VaR)** using historical delta-gamma approximation.
