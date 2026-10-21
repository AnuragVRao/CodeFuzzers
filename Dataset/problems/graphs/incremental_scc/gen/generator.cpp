#include <cstdio>
#include <cstdlib>
#include "random.h"
#include "../params.h"

using namespace std;

int main(int argc, char* argv[]) {
  long long seed = atoll(argv[1]);
  int cap = argc > 2 ? std::min<long long>(atoi(argv[2]), MAX_N) : 0;  // size knob; 0 = original ranges
  auto gen = Random(seed);

  int n = cap ? gen.uniform(1, cap) : seed % 10 + 1;
  int m = gen.uniform<int>(1, cap ? cap : 10);
  printf("%d %d\n", n, m);

  // vertex weight
  for (int i = 0; i < n; ++i) {
    if (i) printf(" ");
    int x = gen.uniform<int>(0, MOD - 1);
    printf("%d", x);
  }
  printf("\n");

  for (int i = 0; i < m; i++) {
    int a = gen.uniform(0, n - 1);
    int b = gen.uniform(0, n - 1);
    printf("%d %d\n", a, b);
  }
  return 0;
}
