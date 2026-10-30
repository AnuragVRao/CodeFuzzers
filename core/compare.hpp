// Output comparison for checker_kind "exact-match" problems.
// same_tokens(a, b) is true when both files contain the same whitespace-separated tokens,
// i.e. differences in spaces, tabs and newlines are ignored (same rule as tools/sanity.py).
// A file that cannot be read compares unequal.
// checker_outcome(exit_code) classifies a "custom" checker's result (see below).
#pragma once
#include <cctype>
#include <cstdio>
#include <string>

inline bool read_file(const std::string& path, std::string& out) {
    FILE* f = fopen(path.c_str(), "rb");
    if (!f) return false;
    out.clear();
    char buf[1 << 16];
    for (size_t n; (n = fread(buf, 1, sizeof buf, f)) > 0;) out.append(buf, n);
    fclose(f);
    return true;
}

inline bool same_tokens(const std::string& path1, const std::string& path2) {
    std::string a, b;
    if (!read_file(path1, a) || !read_file(path2, b)) return false;
    size_t i = 0, j = 0;
    auto skip = [](const std::string& s, size_t& k) { while (k < s.size() && isspace((unsigned char)s[k])) k++; };
    for (;;) {
        skip(a, i), skip(b, j);
        if (i == a.size() || j == b.size()) return i == a.size() && j == b.size();
        for (; i < a.size() && !isspace((unsigned char)a[i]); i++, j++)
            if (j == b.size() || a[i] != b[j]) return false;
        if (j < b.size() && !isspace((unsigned char)b[j])) return false;  // b's token is longer
    }
}

// testlib checker exit code -> test outcome. exit_code is Server::Result::exit_code: the exit status,
// or -signal when killed (a timeout is -SIGALRM). 0 ok; 1 _wa, 2 _pe, 4 _dirt, 8 _unexpected_eof -> "WA";
// 3 _fail (the reference answer judged wrong) -> "ref_fail"; signal, timeout or any other code -> "checker_error".
inline const char* checker_outcome(int exit_code) {
    switch (exit_code) {
        case 0: return "ok";
        case 1: case 2: case 4: case 8: return "WA";
        case 3: return "ref_fail";
        default: return "checker_error";
    }
}
