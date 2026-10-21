#include <iostream>
#include "random.h"
#include "../params.h"

using namespace std;

int main(int argc, char* argv[]) {


    long long seed = atoll(argv[1]);
    int cap = argc > 2 ? std::min<long long>(atoi(argv[2]), N_MAX) : 0;  // size knob; 0 = original ranges
    auto gen = Random(seed);

    int n = gen.uniform(1, cap ? cap : 2'000);

    string s = gen.lower_string(n);

    printf("%s\n", s.c_str());
    return 0;
}
