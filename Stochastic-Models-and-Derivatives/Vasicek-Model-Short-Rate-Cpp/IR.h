// IR.h
#pragma once
#include <vector>

struct IRParams {
    // Vasicek: dr = a(b - r) dt + sigma dW
    double a;        // mean reversion
    double b;        // long-run mean
    double sigma;    // vol of short rate
    double r0;       // initial short rate

    double T;        // maturity of bond (years)
    int    N;        // time steps per path
    int    M;        // number of Monte Carlo paths
};

class IRPricer {
public:
    explicit IRPricer(const IRParams& p): P(p) {}

    // Estimate P(0,T) via Monte Carlo
    double priceZeroCoupon();

private:
    IRParams P;
};

