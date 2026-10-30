// Test generator for core/tests/tape_server_test.cpp, built with Dataset/common/random.h and linked
// with fs_runtime.o. Usage: gen_tape_toy <seed> <n>
//   n > 0:  n lines of uniform(0, 1023) (one word per draw, so n draws = n words)
//   n == 0: one uniform_pair(0, 5) (never ends on an all-zero tape: a == b forever)
//   n == -1: prints whether a tape session is armed ("session 0" / "session 1"), no draws
//   n == -2: draws 100 words (printing them), then abort()
#include <cstdio>
#include <cstdlib>
#include "random.h"

int main(int argc, char* argv[]) {
    long long n = argc > 2 ? atoll(argv[2]) : 0;
    Random gen(atoll(argv[1]));
    if (n == -1) {
        printf("session %d\n", &cf_session != nullptr && cf_session != nullptr);
    } else if (n == -2) {
        for (int i = 0; i < 100; i++) printf("%llu\n", (unsigned long long)gen.uniform<uint64_t>(0, 1023));
        fflush(stdout);
        abort();
    } else if (n == 0) {
        auto [a, b] = gen.uniform_pair(0, 5);
        printf("%d %d\n", a, b);
    } else {
        for (long long i = 0; i < n; i++) printf("%llu\n", (unsigned long long)gen.uniform<uint64_t>(0, 1023));
    }
    return 0;
}
