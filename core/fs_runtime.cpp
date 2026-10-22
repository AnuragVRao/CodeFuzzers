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
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <cerrno>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/time.h>
#include <sys/wait.h>
#include <unistd.h>

namespace {
constexpr int COV_FD = 197, REQ_FD = 198, REP_FD = 199;
constexpr size_t MAP_SIZE = 1 << 16;

struct Request { int32_t timeout_ms; char a1[32]; char a2[32]; };  // same layout in server.hpp
struct Reply { int32_t status; int32_t elapsed_us; };
static_assert(sizeof(Request) == 68 && sizeof(Reply) == 8, "protocol layout");

unsigned char dummy_map[MAP_SIZE];
unsigned char* cov_map = dummy_map;
uint32_t prev_loc = 0;
char arg1[32], arg2[32];  // argv overrides must outlive cf_init's stack frame

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

long long now_us() {
    timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec * 1000000LL + t.tv_nsec / 1000;
}
}  // namespace

// glibc passes argc/argv/envp to ELF constructors.
__attribute__((constructor(101))) static void cf_init(int argc, char** argv, char**) {
    if (fcntl(REQ_FD, F_GETFD) == -1) return;  // not under a fork server: run normally
    if (fcntl(COV_FD, F_GETFD) != -1) {
        void* p = mmap(nullptr, MAP_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED, COV_FD, 0);
        if (p != MAP_FAILED) cov_map = (unsigned char*)p;
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
            close(COV_FD), close(REQ_FD), close(REP_FD);
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
