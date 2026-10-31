// v3 deep bug (docs/v3_roadmap.md, Step V1), included by Dataset/problems/<g>/<p>/sol_bug_deep.cpp only.
// The solution calls cf_deep::begin() first in main() and cf_deep::guard(g1, g2, g3) once after reading the
// first value array. If all three nested guards pass, the first integer token of the output is increased by 1
// (no integer token: " 0" is appended to the first line). Output goes to a memfd and is copied to the real
// stdout at exit, so the perturbation works however and whenever the solution prints.
// The file defines CF_C1, CF_C2, CF_M, CF_C3 (written by tools/deep_calib.py, never by hand) before including.
// -DCF_GUARD_LOG: guard() prints "g1 g2 g3" to stderr and exits 0 (tools/deep_calib.py only).
#pragma once
#include <cstdio>
#include <cstdlib>
#include <iostream>
#include <string>
#include <sys/mman.h>
#include <unistd.h>

namespace cf_deep {
inline int real_fd = -1, mem_fd = -1;
inline bool fired = false;

inline std::string inc(const std::string& t) {  // decimal integer token + 1
    if (t[0] == '-') {  // -k + 1 = -(k - 1)
        std::string k = t.substr(1);
        int i = int(k.size()) - 1;
        while (k[i] == '0') k[i--] = '9';
        k[i]--;
        size_t nz = k.find_first_not_of('0');
        return nz == std::string::npos ? "0" : "-" + k.substr(nz);
    }
    std::string k = t;
    int i = int(k.size()) - 1;
    while (i >= 0 && k[i] == '9') k[i--] = '0';
    return i < 0 ? "1" + k : (k[i]++, k);
}

inline void perturb(std::string& s) {
    for (size_t i = 0; i < s.size();) {
        while (i < s.size() && isspace((unsigned char)s[i])) i++;
        size_t j = i;
        while (j < s.size() && !isspace((unsigned char)s[j])) j++;
        if (j == i) break;
        std::string t = s.substr(i, j - i);
        size_t d = t[0] == '-' ? 1 : 0;
        if (t.size() > d && t.find_first_not_of("0123456789", d) == std::string::npos) {
            s.replace(i, j - i, inc(t));
            return;
        }
        i = j;
    }
    size_t nl = s.find('\n');
    s.insert(nl == std::string::npos ? s.size() : nl, " 0");
}

inline void finish() {
    fflush(stdout);
    std::cout.flush();
    std::string s;
    char buf[1 << 16];
    lseek(mem_fd, 0, SEEK_SET);
    for (ssize_t k; (k = read(mem_fd, buf, sizeof buf)) > 0;) s.append(buf, size_t(k));
    if (fired) perturb(s);
    for (size_t off = 0; off < s.size();) {
        ssize_t k = write(real_fd, s.data() + off, s.size() - off);
        if (k <= 0) break;
        off += size_t(k);
    }
}

inline void begin() {
    real_fd = dup(1);
    mem_fd = memfd_create("cf_deep_out", 0);
    if (real_fd < 0 || mem_fd < 0 || dup2(mem_fd, 1) < 0) abort();
    atexit(finish);
}

inline void guard(long long g1, long long g2, long long g3) {
#ifdef CF_GUARD_LOG
    fprintf(stderr, "%lld %lld %lld\n", g1, g2, g3);
    fflush(stderr);
    _exit(0);
#endif
    long long r = (g3 % CF_M + CF_M) % CF_M;
    if (g1 >= CF_C1) {
        if (g2 >= CF_C2) {
            if (r == CF_C3) fired = true;
        }
    }
}
}  // namespace cf_deep
