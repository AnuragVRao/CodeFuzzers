// Fork-server + coverage runtime, linked into every binary built by tools/build.py (compiled
// WITHOUT coverage flags). Started normally, the binary behaves normally. Started by
// core/server.hpp (fd 198 open), a constructor turns it into a fork server: per request on fd 198
// it forks a child that returns from the constructor and runs main(), and reports
// {wait status, wall-clock µs} on fd 199. trace-pc builds count edge hits (saturating at 255)
// into the map on fd 197; core/fuzzer.cpp turns the counts into hit-count buckets.
//
// Placeholders: the server is started with argv tokens "@SEED@" and/or "@SIZE@" (whole tokens).
// Per request the child overwrites those argv entries with the request's a1 (seed) / a2 (size),
// so a generator can take its arguments in any order ("--seed @SEED@ --n @SIZE@"). Without any
// placeholder the legacy rule applies: argv[1] = a1 and argv[2] = a2.
//
// Tape (generator servers only, docs/tape_design.md): with fd 196 open the server maps that memfd
// (header of offsets/capacities/counters, then input words, output words, draw log; no pointers).
// For a request with arm set the server first clears the header's counters and flags, then forks;
// the child builds a local session from the mapping and points cf_session at it before main(). On a
// normal exit (exit() / return from main) it stores out_len/log_len (capped) and consumed, and LAST
// the flags with TAPE_COMPLETE. A budget exit (_Exit 85), crash or timeout writes no header field,
// so the header stays cleared (COMPLETE = 0). Unarmed requests leave cf_session null (exact v1).
//
// Value profile (v3, docs/v3_roadmap.md Step V2): binaries built with -fsanitize-coverage=trace-cmp call the
// __sanitizer_cov_trace_*cmp* hooks below. If the coverage memfd holds 2 x MAP_SIZE bytes, the second half is the
// value-profile map: one byte per feature (hash of the compare's PC and floor(log2(|a - b| + 1))), set to 1.
// Otherwise the features go to a dummy map. CF_VP_LOG=1 prints every compare ("cmp <pc> <a> <b>") to stderr.

#include <cstddef>
#include <cstdio>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <cerrno>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/wait.h>
#include <unistd.h>

// Tape session pointer declared weak in Dataset/common/random.h. Defined here so binaries with this
// runtime have the symbol; null = no session = exact v1 generator behaviour. This file must not
// include random.h (it defines global_gen), so the two structs are copied from it verbatim; the
// static_asserts here and in core/tests/tape_test.cpp pin both copies to the same layout.
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
constexpr int TAPE_FD = 196, COV_FD = 197, REQ_FD = 198, REP_FD = 199;
constexpr size_t MAP_SIZE = 1 << 16;
constexpr uint64_t TAPE_MAGIC = 0x4346544150450001ULL;  // "CFTAPE" v1
constexpr uint64_t TAPE_COMPLETE = 4;                  // header flag; 1, 2 = CF_TAPE_OVERFLOW, CF_TAPE_BUDGET

struct Request {  // same layout in server.hpp
    int32_t timeout_ms;
    uint32_t arm, fallback_zero, pad;  // arm: give the child a tape session
    uint64_t in_len, budget;           // input words at in_off; budget in words (0 = no limit)
    char a1[32], a2[32];
};
struct Reply { int32_t status; int32_t elapsed_us; };
static_assert(sizeof(Request) == 96 && sizeof(Reply) == 8, "protocol layout");

struct TapeHeader {  // same layout in server.hpp; byte offsets from the start of the mapping
    uint64_t magic, cap, log_cap, in_off, out_off, log_off;  // set by the worker at start
    uint64_t out_len, log_len, consumed, flags;               // cleared by the server per armed request, written by the child at exit
};
static_assert(sizeof(TapeHeader) == 80, "protocol layout");

unsigned char dummy_map[MAP_SIZE], dummy_vp[MAP_SIZE];
unsigned char* cov_map = dummy_map;
unsigned char* vp_map = dummy_vp;
bool vp_log = false;
uint32_t prev_loc = 0;
char arg1[32], arg2[32];  // argv overrides must outlive cf_init's stack frame
TapeHeader* tape = nullptr;  // mapping of fd 196 (generator servers in tape mode only)
size_t tape_size = 0;
cf_tape_session session;     // the child's local session (pointers into the mapping)

bool read_full(int fd, void* buf, size_t n) {
    for (char* p = (char*)buf; n > 0;) {
        ssize_t r = read(fd, p, n);
        if (r < 0 && errno == EINTR) continue;
        if (r <= 0) return false;
        p += r, n -= r;
    }
    return true;
}

void redirect(const char* path, int flags, int target) {
    if (!path) return;
    int fd = open(path, flags, 0644);
    if (fd < 0) _exit(126);  // reported to the client as a crash
    dup2(fd, target);
    close(fd);
}

void store_tape() {  // atexit in an armed child: report the session's counters, COMPLETE last
    tape->out_len = session.out_len < session.out_cap ? session.out_len : session.out_cap;
    tape->log_len = session.log_len < session.log_cap ? session.log_len : session.log_cap;
    tape->consumed = session.out_len;
    __atomic_store_n(&tape->flags, session.flags | TAPE_COMPLETE, __ATOMIC_RELEASE);
}

void arm_tape(const Request& rq) {  // child, before main(): session from offsets + request fields
    if (!tape || tape->magic != TAPE_MAGIC || rq.in_len > tape->cap || tape->in_off + 8 * tape->cap > tape_size ||
        tape->out_off + 8 * tape->cap > tape_size || tape->log_off + sizeof(cf_draw) * tape->log_cap > tape_size)
        _exit(126);  // reported to the client as a crash
    char* base = (char*)tape;
    session = {(const uint64_t*)(base + tape->in_off), rq.in_len, 0, (uint64_t*)(base + tape->out_off), tape->cap, 0,
               (cf_draw*)(base + tape->log_off), tape->log_cap, 0, rq.budget, 0, rq.fallback_zero};
    cf_session = &session;
    atexit(store_tape);
}

long long now_us() {
    timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec * 1000000LL + t.tv_nsec / 1000;
}
}  // namespace

// glibc passes argc/argv/envp to ELF constructors.
__attribute__((constructor(101))) static void cf_init(int argc, char** argv, char**) {
    vp_log = getenv("CF_VP_LOG") != nullptr;
    if (fcntl(REQ_FD, F_GETFD) == -1) return;  // not under a fork server: run normally
    struct stat st;
    if (fcntl(COV_FD, F_GETFD) != -1) {
        bool vp = fstat(COV_FD, &st) == 0 && size_t(st.st_size) >= 2 * MAP_SIZE;
        void* p = mmap(nullptr, vp ? 2 * MAP_SIZE : MAP_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED, COV_FD, 0);
        if (p != MAP_FAILED) cov_map = (unsigned char*)p, vp_map = vp ? cov_map + MAP_SIZE : dummy_vp;
    }
    if (fcntl(TAPE_FD, F_GETFD) != -1 && fstat(TAPE_FD, &st) == 0 && size_t(st.st_size) >= sizeof(TapeHeader)) {
        void* p = mmap(nullptr, st.st_size, PROT_READ | PROT_WRITE, MAP_SHARED, TAPE_FD, 0);
        if (p != MAP_FAILED) tape = (TapeHeader*)p, tape_size = st.st_size;
    }
    int idx_seed = 0, idx_size = 0;  // argv index of @SEED@ / @SIZE@ (0 = absent)
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "@SEED@")) idx_seed = i;
        if (!strcmp(argv[i], "@SIZE@")) idx_size = i;
    }
    for (;;) {
        Request rq;
        if (!read_full(REQ_FD, &rq, sizeof rq)) _exit(0);  // client closed the pipe
        long long t0 = now_us();
        if (rq.arm && tape) tape->out_len = tape->log_len = tape->consumed = tape->flags = 0;
        pid_t pid = fork();
        if (pid == 0) {  // child: become a normal run of main()
            if (idx_seed || idx_size) {
                if (idx_seed) memcpy(arg1, rq.a1, 31), argv[idx_seed] = arg1;
                if (idx_size && rq.a2[0]) memcpy(arg2, rq.a2, 31), argv[idx_size] = arg2;
            } else {
                if (rq.a1[0] && argc > 1) memcpy(arg1, rq.a1, 31), argv[1] = arg1;
                if (rq.a2[0] && argc > 2) memcpy(arg2, rq.a2, 31), argv[2] = arg2;
            }
            redirect(getenv("CF_IN"), O_RDONLY, 0);
            redirect(getenv("CF_OUT"), O_WRONLY | O_CREAT | O_TRUNC, 1);
            close(TAPE_FD), close(COV_FD), close(REQ_FD), close(REP_FD);
            if (rq.arm) arm_tape(rq);
            itimerval it{};
            it.it_value.tv_sec = rq.timeout_ms / 1000;
            it.it_value.tv_usec = rq.timeout_ms % 1000 * 1000;
            setitimer(ITIMER_REAL, &it, nullptr);  // default SIGALRM action kills the child
            prev_loc = 0;
            return;
        }
        int status = 255 << 8;  // fork failure looks like "exit 255"
        if (pid > 0)
            while (waitpid(pid, &status, 0) < 0 && errno == EINTR) {}
        Reply rp{status, int32_t(now_us() - t0)};
        if (write(REP_FD, &rp, sizeof rp) != sizeof rp) _exit(0);
    }
}

// Called on every basic block of binaries built with -fsanitize-coverage=trace-pc.
extern "C" void __sanitizer_cov_trace_pc() {
    uint64_t x = (uint64_t)__builtin_return_address(0);
    x ^= x >> 33, x *= 0xff51afd7ed558ccdULL, x ^= x >> 33;  // mix the PC
    uint32_t cur = x & 0xFFFF;
    uint8_t& m = cov_map[cur ^ prev_loc];  // saturating hit count per edge
    if (m != 255) ++m;
    prev_loc = cur >> 1;
}

// Value profile (trace-cmp). Operands of narrow compares are sign-extended; |a - b| = min(a - b, b - a) mod 2^64,
// which is the distance for both signed and unsigned operands.
static inline void vp_feature(uint64_t pc, uint64_t a, uint64_t b) {
    uint64_t d = a - b;
    if (b - a < d) d = b - a;
    uint64_t x = pc ^ (uint64_t(63 - __builtin_clzll(d + 1)) << 56);  // d <= 2^63, so d + 1 does not wrap
    x ^= x >> 33, x *= 0xff51afd7ed558ccdULL, x ^= x >> 33;
    vp_map[x & 0xFFFF] = 1;
    if (vp_log) fprintf(stderr, "cmp %#llx %lld %lld\n", (unsigned long long)pc, (long long)a, (long long)b);
}
#define CF_PC ((uint64_t)__builtin_return_address(0))
extern "C" {
void __sanitizer_cov_trace_cmp1(uint8_t a, uint8_t b) { vp_feature(CF_PC, int8_t(a), int8_t(b)); }
void __sanitizer_cov_trace_cmp2(uint16_t a, uint16_t b) { vp_feature(CF_PC, int16_t(a), int16_t(b)); }
void __sanitizer_cov_trace_cmp4(uint32_t a, uint32_t b) { vp_feature(CF_PC, int32_t(a), int32_t(b)); }
void __sanitizer_cov_trace_cmp8(uint64_t a, uint64_t b) { vp_feature(CF_PC, a, b); }
void __sanitizer_cov_trace_const_cmp1(uint8_t a, uint8_t b) { vp_feature(CF_PC, int8_t(a), int8_t(b)); }
void __sanitizer_cov_trace_const_cmp2(uint16_t a, uint16_t b) { vp_feature(CF_PC, int16_t(a), int16_t(b)); }
void __sanitizer_cov_trace_const_cmp4(uint32_t a, uint32_t b) { vp_feature(CF_PC, int32_t(a), int32_t(b)); }
void __sanitizer_cov_trace_const_cmp8(uint64_t a, uint64_t b) { vp_feature(CF_PC, a, b); }
void __sanitizer_cov_trace_cmpf(float, float) {}   // floating-point compares carry no value-profile feature
void __sanitizer_cov_trace_cmpd(double, double) {}
void __sanitizer_cov_trace_switch(uint64_t v, uint64_t* cases) {  // cases = {count, bit width, values...}
    for (uint64_t i = 0; i < cases[0]; i++) vp_feature(CF_PC + i, v, cases[2 + i]);
}
}
