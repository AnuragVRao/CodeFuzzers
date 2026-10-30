// File-based tape runtime (roadmap Step S, docs/tape_design.md), linked into the build/tape/<problem>/ generators
// instead of fs_runtime.o (no fork server). Before main() it arms a tape session from environment variables:
//   CF_TAPE_IN             file of raw little-endian uint64 input words (absent = empty tape)
//   CF_TAPE_OUT            file that receives the output tape (every word consumed, raw uint64) at exit
//   CF_TAPE_LOG            file that receives the draw log at exit (raw {uint64 index, uint64 upper} pairs)
//   CF_TAPE_FALLBACK_ZERO  "1": past the input tape, words read 0 instead of this instance's xoshiro
//   CF_TAPE_BUDGET         max words consumed (default 1,000,000; 0 = no limit); exceeding it exits with code 85
// The files are written only on a normal exit (exit() or return from main); a budget exit, crash or timeout writes
// nothing. With no CF_TAPE_* variable the session has an empty tape, so the output is identical to v1 (golden test).
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

// Copied verbatim from Dataset/common/random.h (this file must not include it: it defines global_gen); the
// static_asserts here, in fs_runtime.cpp and in core/tests/tape_test.cpp pin all copies to the same layout.
struct cf_draw { uint64_t index, upper; };  // index of the ACCEPTED word in the output tape
struct cf_tape_session {
    const uint64_t* in;  uint64_t in_len, in_pos;
    uint64_t* out;       uint64_t out_cap, out_len;  // out_len counts every word, even past out_cap
    cf_draw* log;        uint64_t log_cap, log_len;  // log_len counts every draw, even past log_cap
    uint64_t budget;     // max words consumed (0 = no limit); exceeding it exits with CF_TAPE_BUDGET_EXIT
    uint32_t flags;      // CF_TAPE_OVERFLOW | CF_TAPE_BUDGET
    uint32_t fallback_zero;
};
static_assert(sizeof(cf_draw) == 16 && sizeof(cf_tape_session) == 88 && offsetof(cf_tape_session, budget) == 72 &&
              offsetof(cf_tape_session, flags) == 80 && offsetof(cf_tape_session, fallback_zero) == 84, "random.h layout");
cf_tape_session* cf_session = nullptr;

namespace {
constexpr uint64_t DEFAULT_BUDGET = 1000000, UNLIMITED_CAP = 1ULL << 24;
cf_tape_session session;
const char *out_path, *log_path;

void write_file(const char* path, const void* data, size_t bytes) {
    FILE* f = fopen(path, "wb");
    if (!f || fwrite(data, 1, bytes, f) != bytes || fclose(f)) std::_Exit(126);  // reported as a crash
}

void store() {  // atexit: the consumed words and the draw log (an overflow is impossible: cap > budget)
    if (out_path) write_file(out_path, session.out, 8 * (session.out_len < session.out_cap ? session.out_len : session.out_cap));
    if (log_path) write_file(log_path, session.log, sizeof(cf_draw) * (session.log_len < session.log_cap ? session.log_len : session.log_cap));
}

__attribute__((constructor(101))) void arm() {
    const char* budget = getenv("CF_TAPE_BUDGET");
    const char* zero = getenv("CF_TAPE_FALLBACK_ZERO");
    session.budget = budget ? strtoull(budget, nullptr, 10) : DEFAULT_BUDGET;
    session.fallback_zero = zero && !strcmp(zero, "1");
    if (const char* in = getenv("CF_TAPE_IN")) {
        FILE* f = fopen(in, "rb");
        if (!f) std::_Exit(126);
        fseek(f, 0, SEEK_END);
        long bytes = ftell(f);
        fseek(f, 0, SEEK_SET);
        uint64_t* words = (uint64_t*)malloc(bytes > 0 ? bytes : 1);
        if (bytes % 8 || !words || fread(words, 1, bytes, f) != size_t(bytes)) std::_Exit(126);
        fclose(f);
        session.in = words, session.in_len = bytes / 8;
    }
    // every consumed word fits: the budget (or the unlimited cap) bounds out_len, the log has at most one entry per word
    uint64_t cap = (session.budget ? session.budget : UNLIMITED_CAP) + 1;
    session.out = (uint64_t*)malloc(8 * cap), session.out_cap = cap;
    session.log = (cf_draw*)malloc(sizeof(cf_draw) * cap), session.log_cap = cap;
    if (!session.out || !session.log) std::_Exit(126);
    out_path = getenv("CF_TAPE_OUT"), log_path = getenv("CF_TAPE_LOG");
    cf_session = &session;
    atexit(store);
}
}  // namespace
