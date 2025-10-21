// FX.h
#pragma once
#include <vector>

struct FXParams {
    double T;        // maturity (years)
    double K;        // strike
    double S0;       // spot
    double sigma;    // volatility
    double r_d;      // domestic rate
    double r_f;      // foreign rate
    int    N;        // space steps
    int    M;        // time steps
    double Smax;     // upper S boundary
};

class FXPricer {
public:
    explicit FXPricer(const FXParams& p): P(p) {}

    // Returns premium; can optionally fill the last-time grid for inspection
    double price(std::vector<double>* out_S = nullptr,
                 std::vector<double>* out_V0 = nullptr);

private:
    FXParams P;
    double interpolate(const std::vector<double>& Sgrid,
                       const std::vector<double>& V,
                       double x) const;
};
