// Authored for CodeFuzzers (not part of Library Checker). SPDX-License-Identifier: Apache-2.0
// Deliberately naive reference: obviously correct, only meant for small inputs.
// a_i = length of the longest common prefix of S and S.substr(i), by direct comparison.
#include <cstdio>
#include <string>
using namespace std;
int main() {
    static char buf[1 << 20];
    scanf("%s", buf);
    string s = buf;
    int n = s.size();
    for (int i = 0; i < n; i++) {
        int k = 0;
        while (i + k < n && s[k] == s[i + k]) k++;
        printf("%d%c", k, i + 1 == n ? '\n' : ' ');
    }
    return 0;
}
