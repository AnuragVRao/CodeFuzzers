// Test generator that reads only argv[1] (the seed) and prints a fixed-size output.
#include <cstdio>
#include <cstdlib>
#include <random>

int main(int argc, char** argv) {
    std::mt19937_64 rng(argc > 1 ? strtoull(argv[1], nullptr, 10) : 0);
    for (int i = 0; i < 10; i++) printf("%llu\n", (unsigned long long)(rng() % 1000000));
}
