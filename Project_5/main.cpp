// maineq1.cpp
// Monte Carlo pricing of a European Call Option

#include "random.h"
#include <iostream>
#include <cmath>
#include <algorithm>

using namespace std;

int main()
{
    cout << "\n*** START EQ1: Monte Carlo European Call ***\n";

    // STEP 1: INPUT PARAMETERS
    double T = 1.0;      // maturity (years)
    double K = 100.0;    // strike
    double S0 = 100.0;   // spot price
    double sigma = 0.10; // volatility
    double r = 0.05;     // risk-free rate
    int N = 500;         // time steps per path
    int M = 10000;       // number of Monte Carlo simulations

    double dt = T / N;
    double sumpayoff = 0.0;

    // STEP 2: MAIN SIMULATION LOOP
    for (int j = 0; j < M; ++j)
    {
        double S = S0; // reset price path

        // STEP 3: TIME INTEGRATION LOOP
        for (int i = 0; i < N; ++i)
        {
            double epsilon = SampleBoxMuller();
            S *= (1 + r * dt + sigma * sqrt(dt) * epsilon);
        }

        // STEP 4: COMPUTE PAYOFF
        sumpayoff += max(S - K, 0.0);
    }

    // STEP 5: DISCOUNTED EXPECTED PAYOFF
    double premium = exp(-r * T) * (sumpayoff / M);

    // STEP 6: OUTPUT RESULTS
    cout << "Option premium = " << premium << endl;
    cout << "*** END EQ1 ***\n";

    return 0;
}
