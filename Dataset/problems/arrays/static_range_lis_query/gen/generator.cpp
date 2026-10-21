#include <algorithm>
#include <cstdlib>

#include "../params.h"
#include "base.hpp"
#include "random.h"

int main(int argc, char *argv[]) {
  const int case_index = std::atoll(argv[1]);
  int cap = argc > 2 ? std::min<long long>(atoi(argv[2]), N_MAX) : 0;  // size knob; 0 = original ranges
  Random gen(case_index ^ 584641959168880510ULL);

  const int N = gen.uniform<int>(N_MIN, cap ? cap : std::min<int>(1000, N_MAX));
  const int Q = gen.uniform<int>(Q_MIN, cap ? cap : std::min<int>(1000, Q_MAX));

  generate(gen, N, Q);

  return 0;
}
