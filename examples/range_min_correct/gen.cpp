#include "random.h"
#include <tuple>
#define N_AND_Q_MAX (long long)500000
#define A_AND_X_ABS_MAX (long long)1000000000

using namespace std;

int main(int argc, char* argv[]) {
    long long seed = atoll(argv[1]);
    int cap = argc > 2 ? std::min<long long>(atoi(argv[2]), N_AND_Q_MAX) : 0;  // size knob; 0 = original ranges
    auto gen = Random(seed);

    int n = gen.uniform<int>(1, cap ? cap : 2000);
    int q = gen.uniform<int>(1, cap ? cap : 2000);
    printf("%d %d\n", n, q);
    for (int i = 0; i < n; i++) {
        int a = gen.uniform<int>(-A_AND_X_ABS_MAX, A_AND_X_ABS_MAX);
        printf("%d", a);
        if (i != n - 1) printf(" ");
    }
    printf("\n");
    for (int i = 0; i < q; i++) {
        int t = gen.uniform(0, 1);
        printf("%d ", t);
        if (t == 0) {
            int l, r;
            tie(l, r) = gen.uniform_pair(0, n);
            int x = gen.uniform<int>(-A_AND_X_ABS_MAX, A_AND_X_ABS_MAX);
            printf("%d %d %d\n", l, r, x);
        } else {
            int l, r;
            tie(l, r) = gen.uniform_pair(0, n);
            printf("%d %d\n", l, r);
        }
    }
    return 0;
}
