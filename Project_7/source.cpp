// FX1_source.cpp
#include "FX.h"
#include "matrix.h"
#include <algorithm>
#include <cmath>

using std::vector;

// Linear interpolation helper
double FXPricer::interpolate(const vector<double>& X,
                             const vector<double>& Y,
                             double x) const {
    if (x <= X.front()) return Y.front();
    if (x >= X.back())  return Y.back();
    auto it = std::upper_bound(X.begin(), X.end(), x);
    int i1 = int(it - X.begin());
    int i0 = i1 - 1;
    double w = (x - X[i0]) / (X[i1] - X[i0]);
    return (1.0 - w) * Y[i0] + w * Y[i1];
}

double FXPricer::price(std::vector<double>* out_S, std::vector<double>* out_V0) {
    const double T = P.T, K = P.K, S0 = P.S0, sigma = P.sigma;
    const double rd = P.r_d, rf = P.r_f;
    const int    N = P.N,   M = P.M;
    const double Smax = P.Smax;

    const double dS = Smax / N;
    const double dt = T / M;

    // grids
    vector<double> S(N + 1);
    for (int i = 0; i <= N; ++i) S[i] = i * dS;

    // value grid at current and next time levels
    vector<double> V(N + 1), Vnext(N + 1);

    // terminal payoff at t = T
    for (int i = 0; i <= N; ++i)
        V[i] = std::max(S[i] - K, 0.0);

    // explicit FD coefficients depend on i (index along S-grid)
    // marching backward in time
    for (int n = M; n > 0; --n) {
        double t = (n - 1) * dt; // time after stepping (used in boundary)

        // boundary at S=0 (call -> 0)
        Vnext[0] = 0.0;

        // boundary at S=Smax (asymptotic: S*e^{-rf (T-t)} - K e^{-rd (T-t)})
        Vnext[N] = Smax * std::exp(-rf * (T - t)) - K * std::exp(-rd * (T - t));
        if (Vnext[N] < 0.0) Vnext[N] = 0.0; // guard for early times

        for (int i = 1; i < N; ++i) {
            double i_d = static_cast<double>(i);
            // coefficients for explicit scheme on uniform S-grid
            double A = 0.5 * dt * (sigma*sigma * i_d*i_d - (rd - rf) * i_d);
            double B = 1.0 - dt * (sigma*sigma * i_d*i_d + rd);
            double C = 0.5 * dt * (sigma*sigma * i_d*i_d + (rd - rf) * i_d);

            Vnext[i] = A * V[i - 1] + B * V[i] + C * V[i + 1];
        }
        V.swap(Vnext);
    }

    if (out_S)   *out_S = S;
    if (out_V0)  *out_V0 = V;

    // interpolate V(S, t=0) at S0
    return interpolate(S, V, S0);
}
