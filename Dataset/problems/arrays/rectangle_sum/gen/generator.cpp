#include "random.h"
#include <iostream>
#include <tuple>

using namespace std;

int main(int argc, char* argv[]) {

    long long seed = atoll(argv[1]);
    int cap = argc > 2 ? atoi(argv[2]) : 0;  // size knob; 0 = original ranges
    auto gen = Random(seed);

    int n = gen.uniform(1, cap ? cap : 1'000);
    int q = gen.uniform(1, cap ? cap : 1'000);
    printf("%d %d\n", n, q);
    for (int i = 0; i < n; i++) {
        int x = gen.uniform(0, 1000);
        int y = gen.uniform(0, 1000);
        int w = gen.uniform(0, 1'000'000'000);
        printf("%d %d %d\n", x, y, w);
    }
    for (int i = 0; i < q; i++) {
        int l, d, r, u;
        tie(l, r) = gen.uniform_pair(0, 1000);
        tie(d, u) = gen.uniform_pair(0, 1000);
        printf("%d %d %d %d\n", l, d, r, u);
    }
    return 0;
}