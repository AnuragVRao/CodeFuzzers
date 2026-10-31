// v3 deep bug (docs/v3_roadmap.md, Step V1), included by Dataset/problems/<g>/<p>/sol_bug_deep.cpp only.
// The solution calls cf_deep::begin() first in main() and cf_deep::guard(g1, g2, g3) once after reading the
// first value array. If all three nested guards pass, the first integer token of the output is increased by 1
// (no integer token: " 0" is appended to the first line). Output goes to a memfd and is copied to the real
// stdout at exit, so the perturbation works however and whenever the solution prints.
// The file defines CF_C1, CF_C2, CF_M, CF_C3 (written by tools/deep_calib.py, never by hand) before including.
// -DCF_GUARD_LOG: guard() prints "g1 g2 g3" to stderr and exits 0 (tools/deep_calib.py only).
// -DCF_NO_PERTURB (fast_bug_deep_noperturb, V3 pre-pilot smoke runs only): the guard comparisons are kept and
// instrumented, the innermost body writes a volatile sink instead, the output is never changed, nothing is logged.
// Only guard() is instrumented: the capture/rewrite helpers are no_sanitize_coverage (and use no std::string, whose
// template code would be instrumented), so they add no edge or value-profile features.
#pragma once
#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <sys/mman.h>
#include <unistd.h>

#define CF_NOCOV __attribute__((no_sanitize_coverage, noinline))

namespace cf_deep {
inline int real_fd = -1, mem_fd = -1;
inline bool fired = false;
inline volatile int sink = 0;

CF_NOCOV inline void write_all(const char* p, size_t n) {
    while (n > 0) {
        ssize_t k = write(real_fd, p, n);
        if (k <= 0) return;
        p += k, n -= size_t(k);
    }
}

// Writes buf[0, n) to the real stdout with the first integer token increased by 1 (or " 0" appended to line 1).
CF_NOCOV inline void write_perturbed(const char* s, size_t n) {
    for (size_t i = 0; i < n;) {
        while (i < n && isspace((unsigned char)s[i])) i++;
        size_t j = i;
        while (j < n && !isspace((unsigned char)s[j])) j++;
        if (j == i) break;
        size_t d = s[i] == '-' ? i + 1 : i, k = d;
        while (k < j && s[k] >= '0' && s[k] <= '9') k++;
        if (k == j && j > d) {  // integer token s[i, j)
            char* t = (char*)malloc(j - i + 2);  // room for one more digit
            size_t len = j - d;
            memcpy(t + 1, s + d, len);
            char* x = t + 1;
            if (s[i] != '-') {  // x + 1
                long long q = (long long)len - 1;
                while (q >= 0 && x[q] == '9') x[q--] = '0';
                if (q < 0) *--x = '1', len++;
                else x[q]++;
            } else {  // -x + 1 = -(x - 1)
                long long q = (long long)len - 1;
                while (x[q] == '0') x[q--] = '9';
                x[q]--;
                while (len > 1 && *x == '0') x++, len--;
                if (!(len == 1 && *x == '0')) *--x = '-', len++;
            }
            write_all(s, i), write_all(x, len), write_all(s + j, n - j);
            free(t);
            return;
        }
        i = j;
    }
    const char* nl = (const char*)memchr(s, '\n', n);
    size_t cut = nl ? size_t(nl - s) : n;
    write_all(s, cut), write_all(" 0", 2), write_all(s + cut, n - cut);
}

CF_NOCOV inline void finish() {
    fflush(stdout);
    std::cout.flush();
    size_t n = size_t(lseek(mem_fd, 0, SEEK_END));
    char* s = (char*)malloc(n + 1);
    size_t got = 0;
    lseek(mem_fd, 0, SEEK_SET);
    for (ssize_t k; got < n && (k = read(mem_fd, s + got, n - got)) > 0;) got += size_t(k);
    if (fired) write_perturbed(s, got);
    else write_all(s, got);
    free(s);
}

CF_NOCOV inline void begin() {
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
            if (r == CF_C3) {
#ifdef CF_NO_PERTURB
                sink = 1;
#else
                fired = true;
#endif
            }
        }
    }
}
}  // namespace cf_deep
