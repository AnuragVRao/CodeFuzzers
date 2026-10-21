// Authored for CodeFuzzers (not part of Library Checker). SPDX-License-Identifier: Apache-2.0
// Uses Library Checker's common/random.h so a given seed always yields the same input.
// Usage: ./generator <seed> [size]   (size = max length/number of elements, default 16)
#include <cstdio>
#include <cstdlib>
#include <string>
#include "random.h"

// S and T over lowercase letters and '*' (wildcard, matches any letter); 1 <= |T| <= |S|.
int main(int argc, char* argv[]) {
    long long seed = atoll(argv[1]);
    int size = argc > 2 ? atoi(argv[2]) : 16;
    Random gen(seed);
    int n = gen.uniform(1, size), m = gen.uniform(1, n);
    int k = gen.uniform(1, 3);
    int star_pct = gen.uniform(0, 3) * 15;  // 0, 15, 30 or 45 percent wildcards
    auto make = [&](int len) {
        std::string s;
        for (int i = 0; i < len; i++) s += (gen.uniform(0, 99) < star_pct) ? '*' : char('a' + gen.uniform(0, k - 1));
        return s;
    };
    printf("%s\n%s\n", make(n).c_str(), make(m).c_str());
    return 0;
}
