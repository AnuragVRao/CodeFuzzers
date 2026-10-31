// Tape mutation operators (docs/tape_design.md, Mutation), shared by core/fuzzer.cpp and core/part2.cpp.
// mutate() rewrites a child tape (a copy of the parent's output tape) using the parent's draw log; it
// draws only from the given rng, so the fuzzer and the Part 2 tool make identical choices for equal state.
#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <functional>
#include <random>
#include <string>
#include <vector>
#include "server.hpp"

enum Op { VALUE, NUDGE, COPY, SIZE, SPAN, BYTE, SPLICE, OPS };
static const char* const OP_NAMES[OPS] = {"value", "nudge", "copy", "size", "span", "byte", "splice"};

static const double factors[] = {0.5, 0.8, 1, 1, 1.25, 2};  // v1 size-factor op

struct MutCfg {
    bool byte = false;  // --tape-mut byte: one random byte of one random word (diagnostic)
    bool span = false;  // --tape-span 1: span ablation
    bool splice = false;  // v3 --splice 1: mix value 40 / nudge 25 / copy 10 / splice 15 / size 10
    int max_size = 200;
};

// v3 splice donor: a pool entry's tape (words + draw log), handed out by the caller's donor callback.
struct Donor {
    const uint64_t* words;
    uint32_t n_words;
    const TapeDraw* log;
    uint32_t n_draws;
};
using DonorFn = std::function<bool(Donor&)>;

// One applied operator for --op-log: draw ops (value, nudge, copy, span) a = draw index, b = old value, c = new
// value (span: one record per draw); byte: a = word index, b = old word, c = new word; size: a = old size,
// b = new size, factor = the size factor; splice: a = k, b = words kept from the parent, c = first donor word index.
struct OpRec {
    Op op;
    uint64_t a, b, c;
    double factor;
};

static std::string op_text(const std::vector<OpRec>& recs) {
    std::string s;
    char buf[96];
    for (const OpRec& o : recs) {
        if (o.op == SIZE) snprintf(buf, sizeof buf, " size:%llu:%llu:%g", (unsigned long long)o.a, (unsigned long long)o.b, o.factor);
        else snprintf(buf, sizeof buf, " %s:%llu:%llu:%llu", OP_NAMES[o.op], (unsigned long long)o.a, (unsigned long long)o.b, (unsigned long long)o.c);
        s += buf;
    }
    return s;
}

static uint64_t mask_of(uint64_t upper) {  // as in random.h next(upper)
    if (!(upper & (upper + 1))) return upper;
    int lg = 63 - __builtin_clzll(upper);
    return lg == 63 ? ~0ULL : (1ULL << (lg + 1)) - 1;
}
static uint64_t upto(std::mt19937_64& rng, uint64_t upper) {  // uniform in [0, upper]
    return upper == ~0ULL ? rng() : std::uniform_int_distribution<uint64_t>(0, upper)(rng);
}

// Child tape t (a copy of the parent's output tape) with the parent's draw log (n draws); may change
// size. Applies m = min(8, 1 + Geometric(0.5)) operators (docs/tape_design.md, Mutation); returns the
// set of operators actually applied (bit per Op) and counts each application in op_applied[op].
// A draw write replaces the WHOLE accepted word with v; a draw's value is word & mask(upper).
// rec (--op-log only, else null) receives every write; recording never calls rng.
// v3 splice (mc.splice): child = the parent's words for draws 0..k-1 (up to and including draw k-1's accepted
// word), then the donor's words from just after its draw k-1's accepted word; k uniform on [1, min(draws) - 1].
// The donor comes from donor() (the caller picks it from the pool). No donor or min(draws) < 2: a value op instead
// (counted in *splice_fallback). A splice ends the child's operator list (the parent's draw log no longer
// describes the tape after it).
static unsigned mutate(std::vector<uint64_t>& t, const TapeDraw* log, size_t n, uint16_t& size, std::mt19937_64& rng,
                       const MutCfg& mc, long long* op_applied, std::vector<OpRec>* rec, const DonorFn* donor = nullptr,
                       long long* splice_fallback = nullptr) {
    unsigned applied = 0;
    auto apply = [&](Op op) { op_applied[op]++, applied |= 1u << op; };
    if (mc.byte) {  // diagnostic: one random byte of one random word
        if (!t.empty()) {
            size_t i = rng() % t.size();
            uint64_t& x = t[i];
            uint64_t old = x;
            int b = int(rng() % 8);
            x = (x & ~(0xFFULL << (8 * b))) | ((rng() & 0xFF) << (8 * b));
            if (rec) rec->push_back({BYTE, i, old, x, 0});
        }
        apply(BYTE);
        return applied;
    }
    auto val = [&](size_t d) { return t[log[d].index] & mask_of(log[d].upper); };
    auto value_op = [&] {  // new value in [0, upper], different from the old one if upper > 0
        size_t d = rng() % n;
        uint64_t up = log[d].upper, old = val(d), v = 0;
        if (up > 0) v = upto(rng, up - 1), v += v >= old;
        t[log[d].index] = v;
        if (rec) rec->push_back({VALUE, d, old, v, 0});
        apply(VALUE);
    };
    auto nudge_op = [&] {  // nudge by +-k, k in 1..16, clamped to [0, upper]
        size_t d = rng() % n;
        uint64_t up = log[d].upper, old = val(d), k1 = 1 + rng() % 16;
        t[log[d].index] = (rng() & 1) ? (old > up - std::min(up, k1) ? up : old + k1) : (old < k1 ? 0 : old - k1);
        if (rec) rec->push_back({NUDGE, d, old, t[log[d].index], 0});
        apply(NUDGE);
    };
    auto copy_op = [&] {  // copy val(d1) into d2 if it fits; up to 4 retries of d2, then a value op
        size_t d1 = rng() % n;
        uint64_t v = val(d1);
        bool done = false;
        for (int tries = 0; tries < 5 && !done; tries++) {
            size_t d2 = rng() % n;
            if (v <= log[d2].upper) {
                if (rec) rec->push_back({COPY, d2, val(d2), v, 0});
                t[log[d2].index] = v, done = true;
            }
        }
        if (done) apply(COPY);
        else value_op();
    };
    auto splice_op = [&]() -> bool {  // true if applied
        Donor b;
        if (n < 2 || !donor || !*donor || !(*donor)(b) || b.n_draws < 2) return false;
        size_t k = 1 + rng() % (std::min<size_t>(n, b.n_draws) - 1);
        size_t keep = log[k - 1].index + 1, from = b.log[k - 1].index + 1;
        t.resize(keep);
        t.insert(t.end(), b.words + from, b.words + b.n_words);
        if (rec) rec->push_back({SPLICE, k, keep, from, 0});
        apply(SPLICE);
        return true;
    };
    int m = std::min(8, 1 + std::geometric_distribution<int>(0.5)(rng));
    for (int k = 0; k < m; k++) {
        int u = int(rng() % 100);
        if (n == 0 || u >= 90) {  // size (also the only possible op when the parent made no draws)
            double factor = factors[rng() % 6], s = std::llround(size * factor);
            uint16_t old = size;
            size = uint16_t(std::min<double>(std::max<double>(s, 1), mc.max_size));
            if (rec) rec->push_back({SIZE, old, size, 0, factor});
            apply(SIZE);
        } else if (mc.splice) {  // v3 mix: value 40 / nudge 25 / copy 10 / splice 15 (/ size 10 above)
            if (u < 40) value_op();
            else if (u < 65) nudge_op();
            else if (u < 75) copy_op();
            else if (splice_op()) break;
            else {
                if (splice_fallback) ++*splice_fallback;
                value_op();
            }
        } else if (mc.span && u >= 40 && u < 50) {  // span: L = 1 + Geometric(mean 8) draws -> 0 or upper
            size_t d = rng() % n, len = 1 + std::geometric_distribution<int>(1.0 / 9)(rng);
            bool top = rng() & 1;
            for (size_t j = d; j < n && j < d + len; j++) {
                uint64_t old = val(j);
                t[log[j].index] = top ? log[j].upper : 0;
                if (rec) rec->push_back({SPAN, j, old, t[log[j].index], 0});
            }
            apply(SPAN);
        } else if (u < 50) {
            value_op();
        } else if (u < 75) {
            nudge_op();
        } else {
            copy_op();
        }
    }
    return applied;
}
