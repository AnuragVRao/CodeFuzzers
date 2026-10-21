#include <cstdio>
#include "random.h"
#include "../params.h"

using namespace std;

int main(int argc, char* argv[]) {

    long long seed = atoll(argv[1]);
    int cap = argc > 2 ? std::min<long long>(atoi(argv[2]), N_MAX) : 0;  // size knob; 0 = original ranges
    auto gen = Random(seed);

    int n = gen.uniform<int>(N_MIN, cap ? cap : 100);
    int m = gen.uniform<int>(M_MIN, cap ? cap : 200);
    printf("%d %d\n", n, m);
    for (int i = 0; i < m; i++) {
        int a = gen.uniform(0, n - 1);
        int b = gen.uniform(0, n - 1);
        printf("%d %d\n", a, b);
    }
    return 0;
}
