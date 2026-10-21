// Authored for CodeFuzzers (not part of Library Checker). SPDX-License-Identifier: Apache-2.0
// Deliberately naive reference: obviously correct, only meant for small inputs.
// Put every substring into a set and count it.
#include <cstdio>
#include <set>
#include <string>
using namespace std;
int main() {
    static char buf[1 << 20];
    scanf("%s", buf);
    string s = buf;
    int n = s.size();
    set<string> all;
    for (int i = 0; i < n; i++)
        for (int len = 1; i + len <= n; len++) all.insert(s.substr(i, len));
    printf("%lld\n", (long long)all.size());
    return 0;
}
