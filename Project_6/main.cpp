// maineq2.cpp
// Monte Carlo pricing of a two-asset Basket Call Option

#include "random.h"
#include <iostream>
#include <cmath>
#include <algorithm>

using namespace std;

int main()
{
    cout << "\n*** START EQ2: Monte Carlo Basket Call ***\n";

    // Input parameters
    double T = 1.0;         // maturity (years)
    double K = 100.0;       // strike
    double S1_0 = 100.0;    // spot of asset 1
    double S2_0 = 100.0;    // spot of asset 2
    double sigma1 = 0.10;   // volatility of asset 1
    double sigma2 = 0.15;   // volatility of asset 2
    double r = 0.05;        // risk-free rate
    double rho = 0.5;       // correlation
    double w1 = 0.5;        // weight of asset 1
    double w2 = 0.5;        // weight of asset 2

    int N = 500;            // time steps
    int M = 10000;          // Monte Carlo paths
    double dt = T / N;

    double sumPayoff = 0.0;

    // Monte Carlo simulation
    for (int j = 0; j < M; ++j)
    {
        double S1 = S1_0;
        double S2 = S2_0;

        for (int i = 0; i < N; ++i)
        {
            double z1 = SampleBoxMuller();
            double z2p = SampleBoxMuller();
            double z2 = rho * z1 + sqrt(1.0 - rho * rho) * z2p;

            S1 *= (1 + r * dt + sigma1 * sqrt(dt) * z1);
            S2 *= (1 + r * dt + sigma2 * sqrt(dt) * z2);
        }

        double basket = w1 * S1 + w2 * S2;
        sumPayoff += max(basket - K, 0.0);
    }

    double premium = exp(-r * T) * (sumPayoff / M);

    cout << "Basket Option premium = " << premium << endl;
    cout << "*** END EQ2 ***\n";

    return 0;
}
