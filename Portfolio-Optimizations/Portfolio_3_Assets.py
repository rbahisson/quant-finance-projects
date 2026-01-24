import numpy as np 
import matplotlib.pyplot as plt
from scipy.optimize import minimize

mu = np.array([ 0.09, 0.06, 0.12])
sigma = np.array([0.18, 0.12, 0.25])
r_f = 0.02 # Risk-free rate


rho = np.array([[1, 0.20, 0.40], 
               [0.20, 1, 0.10], 
               [0.40, 0.10, 1] ]) # Correlations Matrix

cov = np.outer(sigma, sigma) * rho # Covariance Matrix

omega_0 = np.ones(len(mu)) / len(mu) # Initial guess 

##### Global Minimum Variance Weights

ones = np.ones(3)
inv_cov = np.linalg.inv(cov)
numerator = inv_cov @ ones
denominator = ones.T @ inv_cov @ ones
omega_min_var = numerator / denominator

print("Weights (Minimum Variance):", omega_min_var)
#print("Expected Optimized Portfolio Return (Minimum Variance):", omega_min_var @ mu.T)
#print("Expected Optimized Portfolio Variance (Minimum Variance):", omega_min_var @ cov @ omega_min_var.T)

##### Mean-Variance Utility 

lam = 1 # Risk Aversion

def mean_variance_objective(omega, mu, cov, lam): 
    return 0.5 * lam * (omega @ cov @ omega) - (omega @ mu)

cons = {"type": "eq", "fun": lambda omega: omega.sum() - 1.0}
bounds = [(0.0, None)] * len(mu)

result = minimize(mean_variance_objective, x0= omega_0, args= (mu, cov, lam), constraints=cons, bounds=bounds, method='SLSQP')

omega_mvu = result.x

#print(result.success, result.message)
print("Weights (Mean-Variance Utility):", omega_mvu)

##### Maximize Sharpe Ratio 

def neg_sharpe_ratio_objective(omega, mu, cov, r_f): 
    return - (omega @ mu - r_f) / (np.sqrt(omega.T @ cov @ omega))

result_sharpe = minimize(neg_sharpe_ratio_objective, x0=omega_0, args=(mu, cov, r_f), constraints= cons, bounds=bounds, method='SLSQP')

omega_sharpe = result_sharpe.x

print("Weights (Maximize Sharpe Ratio):", omega_sharpe)

##### Minimum Variance with Target Return 

mu_target = 0.11

def variance_objective(omega, cov): 
    return omega @ cov @ omega.T

cons2 = [
    {"type": "eq", "fun": lambda omega: omega.sum() - 1.0}, 
    {"type": "eq", "fun": lambda omega: (omega @ mu.T) - mu_target}]

results_mvtr = minimize(variance_objective, x0=omega_0, args=(cov), constraints= cons2, bounds=bounds, method='SLSQP')

omega_mvtr = results_mvtr.x

print("Weights (Minimum Variance with Target Return)", omega_mvtr)