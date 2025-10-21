// IR1_main.cpp
#include "IR.h"
#include <iostream>

int main() {
    std::cout << "\n*** START IR1: Vasicek MC for Zero-Coupon Bond ***\n";

    IRParams p;
    p.a = 0.8;       // mean-reversion speed
    p.b = 0.05;      // long-run mean (5%)
    p.sigma = 0.01;  // short-rate vol (1%)
    p.r0 = 0.03;     // initial short rate 3%

    p.T = 2.0;       // bond maturity (2 years)
    p.N = 1000;      // time steps per path
    p.M = 20000;     // Monte Carlo paths

    IRPricer pricer(p);
    double P0T = pricer.priceZeroCoupon();

    std::cout << "Estimated zero-coupon price P(0,T) = " << P0T << "\n";
    std::cout << "*** END IR1 ***\n";
    return 0;
}
