// Authored for CodeFuzzers (not part of Library Checker). SPDX-License-Identifier: Apache-2.0
// Deliberately naive reference: obviously correct, only meant for small inputs.
// A word is Lyndon if it is strictly smaller than each of its proper suffixes.
// The first factor of the Lyndon factorization is the LONGEST Lyndon prefix (Chen-Fox-Lyndon),
// so repeatedly cut the longest Lyndon prefix. Output the cut positions 0 = a_0 < ... < a_k = N.
#include <cstdio>
#include <string>
#include <vector>
using namespace std;
static bool is_lyndon(const string& w) {
    for (size_t i = 1; i < w.size(); i++)
        if (!(w < w.substr(i))) return false;
    return true;
}
int main() {
    static char buf[1 << 20];
    scanf("%s", buf);
    string s = buf;
    int n = s.size();
    vector<int> cuts = {0};
    int pos = 0;
    while (pos < n) {
        int len = n - pos;
        while (!is_lyndon(s.substr(pos, len))) len--;
        pos += len;
        cuts.push_back(pos);
    }
    for (size_t i = 0; i < cuts.size(); i++) printf("%d%c", cuts[i], i + 1 == cuts.size() ? '\n' : ' ');
    return 0;
}
