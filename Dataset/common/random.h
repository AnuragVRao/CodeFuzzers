#pragma once

#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <numeric>
#include <random>
#include <set>

// CodeFuzzers v2 tape session (docs/tape_design.md). cf_session is a weak symbol: it is DEFINED only
// by a runtime (core/fs_runtime.cpp, core/tape_file_runtime.cpp); without one (build/plain/) its
// address is null. Address null or pointer null = exact v1 behaviour. With a session, raw next()
// takes input-tape words first, then this instance's xoshiro (or 0 with fallback_zero; xoshiro does
// not advance while input words are used, so it continues from the seed's first word); every word
// is appended to the output tape and every accepted next(upper) word is logged as a draw.
struct cf_draw { uint64_t index, upper; };  // index of the ACCEPTED word in the output tape
struct cf_tape_session {
    const uint64_t* in;  uint64_t in_len, in_pos;
    uint64_t* out;       uint64_t out_cap, out_len;  // out_len counts every word, even past out_cap
    cf_draw* log;        uint64_t log_cap, log_len;  // log_len counts every draw, even past log_cap
    uint64_t budget;     // max words consumed (0 = no limit); exceeding it exits with CF_TAPE_BUDGET_EXIT
    uint32_t flags;      // CF_TAPE_OVERFLOW | CF_TAPE_BUDGET
    uint32_t fallback_zero;
};
enum : uint32_t { CF_TAPE_OVERFLOW = 1, CF_TAPE_BUDGET = 2 };
constexpr int CF_TAPE_BUDGET_EXIT = 85;
extern cf_tape_session* cf_session __attribute__((weak));

struct Random {
  private:
    // Use xoshiro256**
    // References: http://xoshiro.di.unimi.it/xoshiro256starstar.c
    static uint64_t rotl(const uint64_t x, int k) {
        return (x << k) | (x >> (64 - k));
    }

    std::array<uint64_t, 4> s;

    uint64_t next() {
        if (__builtin_expect(&cf_session != nullptr && cf_session != nullptr, 0)) return tape_next(cf_session);
        return xoshiro();
    }

    uint64_t tape_next(cf_tape_session* t) {
        uint64_t w = t->in_pos < t->in_len ? t->in[t->in_pos++] : t->fallback_zero ? 0 : xoshiro();
        uint64_t i = t->out_len++;
        if (i < t->out_cap) t->out[i] = w;
        else t->flags |= CF_TAPE_OVERFLOW;
        if (t->budget && t->out_len > t->budget) t->flags |= CF_TAPE_BUDGET, std::_Exit(CF_TAPE_BUDGET_EXIT);
        return w;
    }

    // log the draw whose accepted word was the last one returned by next()
    static uint64_t accept(uint64_t r, uint64_t upper) {
        if (__builtin_expect(&cf_session != nullptr && cf_session != nullptr, 0)) {
            cf_tape_session* t = cf_session;
            uint64_t i = t->log_len++;
            if (i < t->log_cap) t->log[i] = {t->out_len - 1, upper};
            else t->flags |= CF_TAPE_OVERFLOW;
        }
        return r;
    }

    uint64_t xoshiro() {
        const uint64_t result_starstar = rotl(s[1] * 5, 7) * 9;

        const uint64_t t = s[1] << 17;

        s[2] ^= s[0];
        s[3] ^= s[1];
        s[1] ^= s[2];
        s[0] ^= s[3];

        s[2] ^= t;

        s[3] = rotl(s[3], 45);

        return result_starstar;
    }

    // random choice from [0, upper]
    uint64_t next(uint64_t upper) {
        if (!(upper & (upper + 1))) {
            // b = 00..0011..11
            return accept(next() & upper, upper);
        }
        int lg = 63 - __builtin_clzll(upper);
        uint64_t mask = (lg == 63) ? ~0ULL : (1ULL << (lg + 1)) - 1;
        while (true) {
            uint64_t r = next() & mask;
            if (r <= upper)
                return accept(r, upper);
        }
    }

  public:
    Random(uint64_t seed = 0) {
        // Use splitmix64
        // Reference: http://xoshiro.di.unimi.it/splitmix64.c
        for (int i = 0; i < 4; i++) {
            uint64_t z = (seed += 0x9e3779b97f4a7c15);
            z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9;
            z = (z ^ (z >> 27)) * 0x94d049bb133111eb;
            s[i] = z ^ (z >> 31);
        }
    }

    // random choice from [lower, upper]
    template <class T>
    T uniform(T lower, T upper) {
        assert(lower <= upper);
        return T(lower + next(uint64_t(upper - lower)));
    }

    // random choice from false or true
    bool uniform_bool() { return uniform(0, 1) == 1; }

    // random choice from [0.0, 1.0]
    double uniform01() {
        uint64_t v = next(1ULL << 63);
        return double(v) / (1ULL << 63);
    }

    // random choice non-empty sub-interval from interval [lower, upper)
    // equal: random choice 2 disjoint elements from [lower, upper]
    template <class T>
    std::pair<T, T> uniform_pair(T lower, T upper) {
        assert(upper - lower >= 1);
        T a, b;
        do {
            a = uniform(lower, upper);
            b = uniform(lower, upper);
        } while (a == b);
        if (a > b) std::swap(a, b);
        return {a, b};
    }

    // generate random lower string that length = n
    std::string lower_string(size_t n) {
        std::string res = "";
        for (size_t i = 0; i < n; i++) {
            res += uniform('a', 'z');
        }
        return res;
    }

    // random shuffle
    template <class Iter>
    void shuffle(Iter first, Iter last) {
        if (first == last) return;
        // Reference and edit:
        // cpprefjp - C++日本語リファレンス
        // (https://cpprefjp.github.io/reference/algorithm/shuffle.html)
        int len = 1;
        for (auto it = first + 1; it != last; it++) {
            len++;
            int j = uniform(0, len - 1);
            if (j != len - 1)
                iter_swap(it, first + j);
        }
    }

    // generate random permutation that length = n
    template <class T>
    std::vector<T> perm(size_t n) {
        std::vector<T> idx(n);
        std::iota(idx.begin(), idx.end(), T(0));
        shuffle(idx.begin(), idx.end());
        return idx;
    }

    // random choise n elements from [lower, upper]
    template <class T>
    std::vector<T> choice(size_t n, T lower, T upper) {
        assert(T(n) <= upper - lower + 1);
        std::set<T> res;
        while (res.size() < n) res.insert(uniform(lower, upper));
        return {res.begin(), res.end()};
    }
} global_gen;

