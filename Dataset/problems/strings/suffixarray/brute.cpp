// Authored for CodeFuzzers (not part of Library Checker). SPDX-License-Identifier: Apache-2.0
// Deliberately naive reference: obviously correct, only meant for small inputs.
// Suffix array = start positions of the non-empty suffixes, sorted by direct string comparison.
#include <algorithm>
#include <cstdio>
#include <numeric>
#include <string>
#include <vector>
using namespace std;
int main() {
    static char buf[1 << 20];
    scanf("%s", buf);
    string s = buf;
    int n = s.size();
    vector<int> sa(n);
    iota(sa.begin(), sa.end(), 0);
    sort(sa.begin(), sa.end(), [&](int a, int b) { return s.compare(a, string::npos, s, b, string::npos) < 0; });
    for (int i = 0; i < n; i++) printf("%d%c", sa[i], i + 1 == n ? '\n' : ' ');
    return 0;
}
