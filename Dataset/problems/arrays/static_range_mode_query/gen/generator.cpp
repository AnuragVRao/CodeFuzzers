// Authored for CodeFuzzers (not part of Library Checker). SPDX-License-Identifier: Apache-2.0
// Uses Library Checker's common/random.h so a given seed always yields the same input.
// Usage: ./generator <seed> [size]   (size = max length/number of elements, default 16)
#include <cstdio>
#include <cstdlib>
#include "random.h"

int main(int argc, char* argv[]) {
    long long seed = atoll(argv[1]);
    int size = argc > 2 ? atoi(argv[2]) : 16;
    Random gen(seed);
    int N = gen.uniform(1, size), Q = gen.uniform(0, 2 * size);
    int domains[] = {1, 2, 3, 5, 10};
    int D = domains[gen.uniform(0, 4)];
    bool big = gen.uniform(0, 3) == 0;   // sometimes use huge values (tests value handling)
    printf("%d %d\n", N, Q);
    for (int i = 0; i < N; i++) {
        long long v = gen.uniform(0, D - 1);
        if (big) v = v * 100000000LL + 7;
        printf("%lld%c", v, i + 1 == N ? '\n' : ' ');
    }
    for (int i = 0; i < Q; i++) {
        int l = gen.uniform(0, N - 1), r = gen.uniform(l + 1, N);
        printf("%d %d\n", l, r);
    }
    return 0;
}
