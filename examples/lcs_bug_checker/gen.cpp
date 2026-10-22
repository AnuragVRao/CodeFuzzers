#include <iostream>
#include "random.h"
#define N_MAX (long long)500000

using namespace std;

int main(int argc, char* argv[]) {
  long long seed = atoll(argv[1]);
  int cap = argc > 2 ? std::min<long long>(atoi(argv[2]), N_MAX) : 0;  // size knob; 0 = original ranges
  auto gen = Random(seed);

  int n = gen.uniform(1, cap ? cap : 5);
  int m = gen.uniform(1, cap ? cap : 5);
  string s, t;
  for (int i = 0; i < n; ++i) s += gen.uniform('a', 'b');
  for (int i = 0; i < m; ++i) t += gen.uniform('a', 'b');
  printf("%s\n", s.c_str());
  printf("%s\n", t.c_str());
  return 0;
}
