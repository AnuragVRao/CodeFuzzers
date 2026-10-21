#include "random.h"
#include <iostream>

using namespace std;

int main(int argc, char *argv[])
{

    long long seed = atoll(argv[1]);
    int cap = argc > 2 ? atoi(argv[2]) : 0;  // size knob; 0 = original ranges
    auto gen = Random(seed);

    int n = gen.uniform(1, cap ? cap : 2000);
    int q = gen.uniform(1, cap ? cap : 2000);
    printf("%d %d\n", n, q);
    for (int i = 0; i < n; i++)
    {
        printf("%d", gen.uniform(0, 1'000'000'000));
        if (i != n - 1)
            printf(" ");
    }
    printf("\n");

    for (int i = 1; i < n; i++)
    {
        printf("%d", gen.uniform(0, i - 1));
        if (i != n - 1)
            printf(" ");
    }
    printf("\n");

    for (int i = 0; i < q; i++)
    {
        int t = gen.uniform(0, 1);
        printf("%d ", t);
        if (t == 0)
        {
            int p = gen.uniform(0, n - 1);
            int x = gen.uniform(0, 1'000'000'000);
            printf("%d %d\n", p, x);
        }
        else
        {
            auto u = gen.uniform(0, n - 1);
            printf("%d\n", u);
        }
    }
    return 0;
}
