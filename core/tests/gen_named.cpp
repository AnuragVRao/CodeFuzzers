// Test generator with named arguments: "--seed S --n N" in any order. Prints N, then N numbers.
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <random>

int main(int argc, char** argv) {
    unsigned long long seed = 0;
    int n = 0;
    for (int i = 1; i + 1 < argc; i += 2) {
        if (!strcmp(argv[i], "--seed")) seed = strtoull(argv[i + 1], nullptr, 10);
        if (!strcmp(argv[i], "--n")) n = atoi(argv[i + 1]);
    }
    std::mt19937_64 rng(seed);
    printf("%d\n", n);
    for (int i = 0; i < n; i++) printf("%llu\n", (unsigned long long)(rng() % 1000000));
}
