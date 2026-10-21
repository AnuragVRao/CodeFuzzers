#include "random.h"
#include <iostream>
#include <tuple>
#include "../params.h"

using namespace std;

int main(int argc, char* argv[]) {
  long long seed = atoll(argv[1]);
  int cap = argc > 2 ? std::min<long long>(atoi(argv[2]), N_AND_Q_MAX) : 0;  // size knob; 0 = original ranges
  auto gen = Random(seed);

  int n = cap ? gen.uniform(1, cap) : seed % 10 + 1;
  int q = cap ? gen.uniform(1, cap) : 1000;
  printf("%d %d\n", n, q);
  for (int i = 0; i < n; i++) {
    int a = gen.uniform<int>(0, MOD - 1);
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
      int b = gen.uniform<int>(1, MOD - 1);
      int c = gen.uniform<int>(0, MOD - 1);
      printf("%d %d %d %d\n", l, r, b, c);
    } else {
      int idx;
      idx = gen.uniform<int>(0, n - 1);
      printf("%d\n", idx);
    }
  }
  return 0;
}
