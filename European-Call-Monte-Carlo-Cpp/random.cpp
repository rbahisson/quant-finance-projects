// random.cpp
// Gaussian deviates using Box–Muller method
#include "random.h"
#include <cstdlib>
#include <cmath>

double SampleBoxMuller()
{
    double x, y, xysquare;
    do
    {
        x = 2.0 * rand() / static_cast<double>(RAND_MAX) - 1;
        y = 2.0 * rand() / static_cast<double>(RAND_MAX) - 1;
        xysquare = x * x + y * y;
    } while (xysquare >= 1.0 || xysquare == 0.0);
    return x * sqrt(-2.0 * log(xysquare) / xysquare);
}
