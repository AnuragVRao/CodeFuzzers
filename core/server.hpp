// Client side of the fork server in core/fs_runtime.cpp, used by fuzzer worker threads.
// A Server is one long-lived process of a binary built by tools/build.py, started with
// posix_spawn (never fork, so it is safe from threads). Requests/replies go through pipes that
// become fds 198/199 in the child; fd 197 is an optional memfd holding the 64 KiB coverage map.
// All our fds are O_CLOEXEC so servers never inherit each other's pipes.
#pragma once
#include <csignal>
#include <cstdint>
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

struct Server {
    struct Result {
        enum Kind { OK, CRASH, TIMEOUT, SERVER_DEAD } kind;
        int exit_code;  // exit status, or -signal number
        int us;         // wall time measured by the server
    };
    static constexpr size_t MAP_SIZE = 1 << 16;
    unsigned char* cov_map = nullptr;  // non-null only when started with_cov

    Server() = default;
    Server(const Server&) = delete;
    Server& operator=(const Server&) = delete;
    ~Server() { stop(); }

    bool start(const std::string& binary, const std::vector<std::string>& args,
               const std::string& cf_in, const std::string& cf_out, bool with_cov) {
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
        posix_spawn_file_actions_t fa;
        posix_spawn_file_actions_init(&fa);
        posix_spawn_file_actions_adddup2(&fa, req[0], 198);
        posix_spawn_file_actions_adddup2(&fa, rep[1], 199);
        if (with_cov) posix_spawn_file_actions_adddup2(&fa, cov_fd, 197);
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
        if (cov_map) memset(cov_map, 0, MAP_SIZE);
        Request rq{};
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

    void stop() {
        if (req_fd >= 0) close(req_fd);  // server sees EOF and exits
        if (rep_fd >= 0) close(rep_fd);
        if (pid > 0) waitpid(pid, nullptr, 0);
        if (cov_map) munmap(cov_map, MAP_SIZE);
        if (cov_fd >= 0) close(cov_fd);
        req_fd = rep_fd = cov_fd = pid = -1;
        cov_map = nullptr;
    }

private:
    struct Request { int32_t timeout_ms; char a1[32]; char a2[32]; };  // same layout in fs_runtime.cpp
    struct Reply { int32_t status; int32_t elapsed_us; };
    static_assert(sizeof(Request) == 68 && sizeof(Reply) == 8, "protocol layout");
    pid_t pid = -1;
    int req_fd = -1, rep_fd = -1, cov_fd = -1;

    // Move fds off 197..199 so the child's dup2 actions cannot clobber each other.
    static int away(int fd) {
        if (fd < 197 || fd > 199) return fd;
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
