#include "random.h"
#include "../params.h"
#include <cstdio>

int main(int argc, char *argv[]) {
    long long seed = atoll(argv[1]);
    int cap = argc > 2 ? std::min<long long>(atoi(argv[2]), N_MAX) : 0;  // size knob; 0 = original ranges
    auto gen = Random(seed);

    int N = cap ? gen.uniform(1, cap) : seed % 500 + 1;
    int Q = cap ? gen.uniform(1, cap) : 1000;
    printf("%d %d\n", N, Q);

    int cand = gen.uniform(0, 1'000'000'000);
    for (int i = 0; i < N; ++i) {
        if (i) {
            printf(" ");
        }
        if (gen.uniform_bool()) {
            printf("%d", cand);
        } else {
            printf("%d", gen.uniform(0, 1'000'000'000));
        }
    }
    printf("\n");

    for (int i = 0; i < Q; ++i) {
        int t = gen.uniform(0, 1);
        printf("%d ", t);
        if (t == 0) {
            int p = gen.uniform(0, N - 1);
            int x = gen.uniform_bool() ? cand : gen.uniform(0, 1'000'000'000);
            printf("%d %d\n", p, x);
        } else {
            auto [l, r] = gen.uniform_pair(0, N);
            printf("%d %d\n", l, r);
        }
    }

    return 0;
}