// IR1_source.cpp
#include "IR.h"
#include "random.h"
#include <cmath>
#include <vector>
#include <numeric>

double IRPricer::priceZeroCoupon() {
    const double a = P.a, b = P.b, sigma = P.sigma;
    const double r0 = P.r0, T = P.T;
    const int N = P.N, M = P.M;

    const double dt = T / static_cast<double>(N);
    double sumDF = 0.0;

    for (int m = 0; m < M; ++m) {
        double r = r0;
        double integral_r = 0.0;

        for (int i = 0; i < N; ++i) {
            // Euler-Maruyama step for Vasicek
            double z = SampleBoxMuller();
            r += a * (b - r) * dt + sigma * std::sqrt(dt) * z;

            // trapezoid/left-Riemann is fine here since dt small:
            integral_r += r * dt;
        }

        double DF = std::exp(-integral_r);  // discount factor along the path
        sumDF += DF;
    }

    return sumDF / static_cast<double>(M);
}
