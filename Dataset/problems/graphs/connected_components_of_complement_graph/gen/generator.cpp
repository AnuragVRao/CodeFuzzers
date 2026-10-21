// Authored for CodeFuzzers (not part of Library Checker). SPDX-License-Identifier: Apache-2.0
// Uses Library Checker's common/random.h so a given seed always yields the same input.
// Usage: ./generator <seed> [size]   (size = max length/number of elements, default 16)
#include <cstdio>
#include <cstdlib>
#include <vector>
#include <utility>
#include <algorithm>
#include "random.h"

// Simple undirected graph. Dense graphs are the interesting case: the complement is then sparse,
// so it has several components.
int main(int argc, char* argv[]) {
    long long seed = atoll(argv[1]);
    int size = argc > 2 ? atoi(argv[2]) : 16;
    Random gen(seed);
    int n = gen.uniform(1, size);
    long long maxm = 1LL * n * (n - 1) / 2;
    long long m;
    int mode = gen.uniform(0, 2);
    if (mode == 0) m = gen.uniform(0LL, std::min<long long>(maxm, n));              // sparse
    else if (mode == 1) m = maxm - gen.uniform(0LL, std::min<long long>(maxm, n));  // nearly complete
    else m = gen.uniform(0LL, maxm);                                                 // anything
    std::vector<std::pair<int, int>> all;
    for (int a = 0; a < n; a++) for (int b = a + 1; b < n; b++) all.push_back({a, b});
    gen.shuffle(all.begin(), all.end());
    all.resize(m);
    printf("%d %d\n", n, (int)m);
    for (auto [a, b] : all) {
        if (gen.uniform_bool()) std::swap(a, b);
        printf("%d %d\n", a, b);
    }
    return 0;
}
