// FX1_main.cpp
#include "FX.h"
#include <iostream>
#include <vector>

int main() {
    std::cout << "\n*** START FX1: Explicit FD European Call (FX) ***\n";

    FXParams p;
    p.T = 1.0;
    p.K = 100.0;
    p.S0 = 100.0;
    p.sigma = 0.20;
    p.r_d = 0.05;     // domestic risk-free
    p.r_f = 0.02;     // foreign risk-free (dividend-like)
    p.N = 400;        // space steps
    p.M = 20000;       // time steps (explicit needs small dt)
    p.Smax = 4.0 * p.K; // far enough upper boundary

    FXPricer pricer(p);

    double premium = pricer.price();
    std::cout << "FX European Call premium = " << premium << "\n";
    std::cout << "*** END FX1 ***\n";
    return 0;
}
