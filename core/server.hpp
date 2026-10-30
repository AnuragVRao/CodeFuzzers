// Client side of the fork server in core/fs_runtime.cpp, used by fuzzer worker threads.
// A Server is one long-lived process of a binary built by tools/build.py, started with
// posix_spawn (never fork, so it is safe from threads). Requests/replies go through pipes that
// become fds 198/199 in the child; fd 197 is an optional memfd holding the 64 KiB coverage map.
// Generator servers can also get a tape memfd on fd 196 (with_tape; docs/tape_design.md): a header
// of offsets/capacities/counters (no pointers) followed by input words, output words and draw log.
// run_tape() arms a session in the child; run() never does. run_gen_with_tape() is the worker API.
// All our fds are O_CLOEXEC so servers never inherit each other's pipes.
#pragma once
#include <csignal>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cerrno>
#include <string>
#include <vector>
#include <fcntl.h>
#include <spawn.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>

extern char** environ;

struct TapeDraw { uint64_t index, upper; };  // = cf_draw in Dataset/common/random.h
struct TapeHeader {                           // same layout in fs_runtime.cpp; byte offsets from the mapping
    uint64_t magic, cap, log_cap, in_off, out_off, log_off;  // set by start()
    uint64_t out_len, log_len, consumed, flags;               // cleared by the server per armed request, written by the child at exit
};

struct Server {
    struct Result {
        enum Kind { OK, CRASH, TIMEOUT, SERVER_DEAD, BUDGET } kind;  // BUDGET: tape word budget exceeded (run_tape only)
        int exit_code;  // exit status, or -signal number
        int us;         // wall time measured by the server
    };
    struct TapeResult {  // spans point into the shared memory: valid only if complete, and only until the next request
        Result res;
        bool complete;                           // the child exited normally and wrote its counters (TAPE_COMPLETE)
        const uint64_t* out;  size_t out_len;   // output tape (<= TAPE_CAP words)
        const TapeDraw* log;  size_t log_len;   // draw log (<= TAPE_LOGCAP entries)
        uint64_t consumed;                       // words consumed (> out_len when the tape overflowed)
        uint32_t flags;                          // TAPE_OVERFLOW | TAPE_BUDGET | TAPE_COMPLETE
    };
    static constexpr size_t MAP_SIZE = 1 << 16;
    static constexpr uint64_t TAPE_CAP = 97930, TAPE_LOGCAP = 79446;  // docs/tape_design.md
    static constexpr uint64_t TAPE_MAGIC = 0x4346544150450001ULL;
    static constexpr uint32_t TAPE_OVERFLOW = 1, TAPE_BUDGET = 2;     // = CF_TAPE_* in random.h
    static constexpr uint32_t TAPE_COMPLETE = 4;                       // set last by a normally exiting child
    static constexpr int TAPE_BUDGET_EXIT = 85;                        // = CF_TAPE_BUDGET_EXIT in random.h
    unsigned char* cov_map = nullptr;  // non-null only when started with_cov
    std::string out_path;              // the child's stdout file (cf_out)
    pid_t server_pid() const { return pid; }

    Server() = default;
    Server(const Server&) = delete;
    Server& operator=(const Server&) = delete;
    ~Server() { stop(); }

    bool start(const std::string& binary, const std::vector<std::string>& args,
               const std::string& cf_in, const std::string& cf_out, bool with_cov, bool with_tape = false) {
        out_path = cf_out;
        signal(SIGPIPE, SIG_IGN);  // a dead server must show up as EPIPE, not kill the fuzzer
        int req[2], rep[2];
        if (pipe2(req, O_CLOEXEC) || pipe2(rep, O_CLOEXEC)) return false;
        req[0] = away(req[0]), rep[1] = away(rep[1]);
        if (with_cov) {
            cov_fd = away(memfd_create("cf_cov", MFD_CLOEXEC));
            if (cov_fd < 0 || ftruncate(cov_fd, MAP_SIZE)) return false;
            void* p = mmap(nullptr, MAP_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED, cov_fd, 0);
            if (p == MAP_FAILED) return false;
            cov_map = (unsigned char*)p;
        }
        if (with_tape) {
            tape_fd = away(memfd_create("cf_tape", MFD_CLOEXEC));
            if (tape_fd < 0 || ftruncate(tape_fd, TAPE_BYTES)) return false;
            void* p = mmap(nullptr, TAPE_BYTES, PROT_READ | PROT_WRITE, MAP_SHARED, tape_fd, 0);
            if (p == MAP_FAILED) return false;
            tape = (TapeHeader*)p;
            *tape = {TAPE_MAGIC, TAPE_CAP, TAPE_LOGCAP, TAPE_IN, TAPE_OUT, TAPE_LOG, 0, 0, 0, 0};
        }
        posix_spawn_file_actions_t fa;
        posix_spawn_file_actions_init(&fa);
        posix_spawn_file_actions_adddup2(&fa, req[0], 198);
        posix_spawn_file_actions_adddup2(&fa, rep[1], 199);
        if (with_cov) posix_spawn_file_actions_adddup2(&fa, cov_fd, 197);
        if (with_tape) posix_spawn_file_actions_adddup2(&fa, tape_fd, 196);
        posix_spawn_file_actions_addopen(&fa, 2, "/dev/null", O_WRONLY, 0);
        posix_spawnattr_t at;
        posix_spawnattr_init(&at);
        sigset_t def;
        sigemptyset(&def);
        sigaddset(&def, SIGPIPE);
        posix_spawnattr_setsigdefault(&at, &def);
        posix_spawnattr_setflags(&at, POSIX_SPAWN_SETSIGDEF);

        std::vector<std::string> env = {"CF_IN=" + cf_in, "CF_OUT=" + cf_out};
        for (char** e = environ; *e; e++)
            if (strncmp(*e, "CF_IN=", 6) && strncmp(*e, "CF_OUT=", 7)) env.push_back(*e);
        std::vector<char*> argv, envp;
        for (auto& s : args) argv.push_back(const_cast<char*>(s.c_str()));
        for (auto& s : env) envp.push_back(const_cast<char*>(s.c_str()));
        argv.push_back(nullptr), envp.push_back(nullptr);

        int rc = posix_spawn(&pid, binary.c_str(), &fa, &at, argv.data(), envp.data());
        posix_spawn_file_actions_destroy(&fa);
        posix_spawnattr_destroy(&at);
        close(req[0]), close(rep[1]);
        req_fd = req[1], rep_fd = rep[0];
        if (rc != 0) pid = -1;
        return rc == 0;
    }

    // a1/a2 replace argv[1]/argv[2] for this run ("" = keep). Zeroes the coverage map first.
    Result run(const std::string& a1, const std::string& a2, int timeout_ms) {
        Request rq{};
        return request(rq, a1, a2, timeout_ms);
    }

    // run() with a tape session in the child: in[0..in_len) is the input tape (copied to shared memory),
    // budget = max words consumed (0 = no limit). Needs start(..., with_tape = true).
    TapeResult run_tape(const std::string& a1, const std::string& a2, int timeout_ms, const uint64_t* in,
                        size_t in_len, bool fallback_zero, uint64_t budget = 0) {
        TapeResult t{};
        if (!tape || in_len > TAPE_CAP) return t.res = {Result::CRASH, 126, 0}, t;
        if (in_len) memcpy((char*)tape + TAPE_IN, in, in_len * sizeof(uint64_t));
        Request rq{};
        rq.arm = 1, rq.fallback_zero = fallback_zero, rq.in_len = in_len, rq.budget = budget;
        t.res = request(rq, a1, a2, timeout_ms);
        if (t.res.kind == Result::CRASH && t.res.exit_code == TAPE_BUDGET_EXIT) t.res.kind = Result::BUDGET;
        t.out = (const uint64_t*)((char*)tape + TAPE_OUT), t.out_len = tape->out_len;
        t.log = (const TapeDraw*)((char*)tape + TAPE_LOG), t.log_len = tape->log_len;
        t.consumed = tape->consumed, t.flags = tape->flags | (t.res.kind == Result::BUDGET ? TAPE_BUDGET : 0);
        t.complete = t.flags & TAPE_COMPLETE;
        return t;
    }

    void stop() {
        if (req_fd >= 0) close(req_fd);  // server sees EOF and exits
        if (rep_fd >= 0) close(rep_fd);
        if (pid > 0) waitpid(pid, nullptr, 0);
        if (cov_map) munmap(cov_map, MAP_SIZE);
        if (cov_fd >= 0) close(cov_fd);
        if (tape) munmap(tape, TAPE_BYTES);
        if (tape_fd >= 0) close(tape_fd);
        req_fd = rep_fd = cov_fd = tape_fd = pid = -1;
        cov_map = nullptr, tape = nullptr;
    }

private:
    struct Request {  // same layout in fs_runtime.cpp
        int32_t timeout_ms;
        uint32_t arm, fallback_zero, pad;
        uint64_t in_len, budget;
        char a1[32], a2[32];
    };
    struct Reply { int32_t status; int32_t elapsed_us; };
    static_assert(sizeof(Request) == 96 && sizeof(Reply) == 8 && sizeof(TapeHeader) == 80, "protocol layout");
    // tape memfd layout: header (padded to 128 bytes) | input words | output words | draw log
    static constexpr uint64_t TAPE_IN = 128, TAPE_OUT = TAPE_IN + 8 * TAPE_CAP, TAPE_LOG = TAPE_OUT + 8 * TAPE_CAP,
                              TAPE_BYTES = TAPE_LOG + sizeof(TapeDraw) * TAPE_LOGCAP;
    pid_t pid = -1;
    int req_fd = -1, rep_fd = -1, cov_fd = -1, tape_fd = -1;
    TapeHeader* tape = nullptr;

    Result request(Request& rq, const std::string& a1, const std::string& a2, int timeout_ms) {
        if (cov_map) memset(cov_map, 0, MAP_SIZE);
        rq.timeout_ms = timeout_ms;
        strncpy(rq.a1, a1.c_str(), sizeof rq.a1 - 1);
        strncpy(rq.a2, a2.c_str(), sizeof rq.a2 - 1);
        Reply rp;
        if (!io(write, req_fd, &rq, sizeof rq) || !io(read, rep_fd, &rp, sizeof rp))
            return {Result::SERVER_DEAD, 0, 0};
        if (WIFSIGNALED(rp.status))
            return {WTERMSIG(rp.status) == SIGALRM ? Result::TIMEOUT : Result::CRASH, -WTERMSIG(rp.status), rp.elapsed_us};
        int code = WEXITSTATUS(rp.status);
        return {code == 0 ? Result::OK : Result::CRASH, code, rp.elapsed_us};
    }

    // Move fds off 196..199 so the child's dup2 actions cannot clobber each other.
    static int away(int fd) {
        if (fd < 196 || fd > 199) return fd;
        int moved = fcntl(fd, F_DUPFD_CLOEXEC, 200);
        close(fd);
        return moved;
    }

    template <class F, class Buf>
    static bool io(F f, int fd, Buf* buf, size_t n) {
        for (char* p = (char*)buf; n > 0;) {
            ssize_t r = f(fd, p, n);
            if (r < 0 && errno == EINTR) continue;
            if (r <= 0) return false;
            p += r, n -= r;
        }
        return true;
    }
};

// Worker API (roadmap Step 2b): run generator gen[variant] (started with_tape) on (seed, size) with a
// tape session; stdout is read from the server's output file. Spans in .tape point into shared memory.
struct GenTapeRun {
    std::string out;
    Server::TapeResult tape;
};
inline GenTapeRun run_gen_with_tape(Server* gen, int variant, int size, uint64_t seed, const uint64_t* in,
                                    size_t in_len, bool fallback_zero, uint64_t budget = 0, int timeout_ms = 2000) {
    GenTapeRun r;
    r.tape = gen[variant].run_tape(std::to_string(seed), std::to_string(size), timeout_ms, in, in_len, fallback_zero, budget);
    if (FILE* f = fopen(gen[variant].out_path.c_str(), "rb")) {
        char buf[1 << 16];
        for (size_t n; (n = fread(buf, 1, sizeof buf, f)) > 0;) r.out.append(buf, n);
        fclose(f);
    }
    return r;
}
