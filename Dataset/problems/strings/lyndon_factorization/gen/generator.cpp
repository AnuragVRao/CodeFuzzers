// Authored for CodeFuzzers (not part of Library Checker). SPDX-License-Identifier: Apache-2.0
// Uses Library Checker's common/random.h so a given seed always yields the same input.
// Usage: ./generator <seed> [size]   (size = max length/number of elements, default 16)
#include <cstdio>
#include <cstdlib>
#include <string>
#include "random.h"
// Mixes plain random strings with the structured shapes where string algorithms tend to break:
// periodic, all-equal, Fibonacci-like and "almost periodic" (one mutated character).
static std::string make_string(Random& gen, int n) {
    int k = gen.uniform(1, 4);
    int mode = gen.uniform(0, 4);
    std::string s;
    auto ch = [&]() { return char('a' + gen.uniform(0, k - 1)); };
    if (mode == 0) {
        for (int i = 0; i < n; i++) s += ch();
    } else if (mode == 1 || mode == 4) {
        int p = gen.uniform(1, n);
        std::string blk;
        for (int i = 0; i < p; i++) blk += ch();
        while ((int)s.size() < n) s += blk;
        s.resize(n);
        if (mode == 4) s[gen.uniform(0, n - 1)] = ch();
    } else if (mode == 2) {
        s = std::string(n, 'a');
    } else {
        std::string a = "a", b = "ab";
        while ((int)b.size() < n) { std::string c = b + a; a = b; b = c; }
        s = b.substr(0, n);
    }
    return s;
}

int main(int argc, char* argv[]) {
    long long seed = atoll(argv[1]);
    int size = argc > 2 ? atoi(argv[2]) : 16;
    Random gen(seed);
    int n = gen.uniform(1, size);
    std::string s = make_string(gen, n);
    printf("%s\n", s.c_str());
    return 0;
}
