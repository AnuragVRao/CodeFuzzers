#include <iostream>
#include <tuple>
#include <vector>

#include "../params.h"
#include "random.h"

int main(int argc, char* argv[]) {
    long long seed = atoll(argv[1]);
    int cap = argc > 2 ? std::min<long long>(atoi(argv[2]), N_MAX) : 0;  // size knob; 0 = original ranges
    auto gen = Random(seed);

    int N = gen.uniform(1, cap ? cap : 1000);
    std::vector<int> par(N, -1);
    for (int i = 1; i < N; i++) {
        par[i] = gen.uniform(0, i - 1);
    }

    using edge = std::pair<int, int>;
    std::vector<edge> edges;
    for (int i = 1; i < N; i++) {
        edges.emplace_back(i, par[i]);
    }

    gen.shuffle(edges.begin(), edges.end());
    printf("%d\n", N);
    for (auto e : edges) {
        int u, v;
        std::tie(u, v) = e;
        printf("%d %d\n", u, v);
    }

    return 0;
}
