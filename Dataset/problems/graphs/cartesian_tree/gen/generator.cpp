#include <iostream>
#include "random.h"
#include "../params.h"

using namespace std;

int main(int argc, char* argv[]) {
    long long seed = atoll(argv[1]);
    int cap = argc > 2 ? std::min<long long>(atoi(argv[2]), N_MAX) : 0;  // size knob; 0 = original ranges
    auto gen = Random(seed);

    // generate params randomly
    int n = cap ? gen.uniform(1, cap) : seed + 1;
    vector<int> a(n);
    set<int> used;
    for (int i = 0; i < n; i++) {
        do {
            a[i] = gen.uniform(A_MIN, A_MIN + n + 3);
        } while (used.count(a[i]));
        used.insert(a[i]);
    }

    // print params
    printf("%d\n", n);
    for (int i = 0; i < n; i++) {
        printf("%d%c", a[i], i + 1 < n ? ' ' : '\n');
    }

    return 0;
}
