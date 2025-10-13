# Project 2 - Quantitative Modeling of Stock Markets Using Regression Models (OLS, Lasso, Ridge, Elastic Net)

This project presents a systematic implementation and comparison of linear modeling methods commonly used in quantitative analysis and machine learning.  
It includes individual notebooks for **Ordinary Least Squares (OLS)**, **Ridge Regression**, **Lasso Regression**, **Elastic Net**, and a **model comparison** study.

Each notebook demonstrates the mathematical foundations, implementation details, and the impact of regularization on model bias–variance tradeoffs.

---

## Workflow Overview

### 1. Ordinary Least Squares (OLS)
- Implement a baseline linear regression model.  
- Fit the model to a dataset and evaluate performance using standard metrics such as Mean Squared Error (MSE) and \( R^2 \).  
- Visualize residuals and fitted values to assess model adequacy.  
- Interpret model coefficients to understand feature relationships.

### 2. Ridge Regression
- Introduce \( L2 \) regularization to penalize large coefficients.  
- Fit models across multiple values of the regularization parameter \( \alpha \).  
- Analyze how increasing regularization reduces overfitting but increases bias.  
- Plot coefficient shrinkage versus regularization strength.

### 3. Lasso Regression
- Apply \( L1 \) regularization to enforce sparsity in model coefficients.  
- Demonstrate variable selection by observing which coefficients shrink to zero.  
- Compare model stability and interpretability against OLS and Ridge models.  
- Use cross-validation to select the optimal \( \alpha \) value.

### 4. Elastic Net
- Combine \( L1 \) and \( L2 \) penalties to balance shrinkage and sparsity.  
- Evaluate model performance across varying `l1_ratio` parameters.  
- Illustrate the tradeoff between Ridge’s stability and Lasso’s sparsity.  
- Discuss Elastic Net’s robustness in correlated predictor settings.

### 5. Model Comparison
- Consolidate results from all regression models.  
- Compare key performance metrics (MSE, \( R^2 \)) and coefficient behavior.  
- Summarize the effect of regularization on prediction accuracy and interpretability.  
- Provide recommendations on model selection for different data conditions.


