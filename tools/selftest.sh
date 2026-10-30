#!/usr/bin/env bash
# End-to-end self-test: build everything, then the golden generator hashes, the fork-server edge cases
# and checker outcome mapping (C++, and Python agreeing with it), the random.h tape session (in-process and
# through the fork-server), the pool correctness
# check (plain and under ThreadSanitizer, with ASLR off because GCC 13 TSan needs it), the tape arena stress
# test (plain and TSan), the
# aggregation self-test, a quick correct-solution sanity run on all problems, and the analysis server's
# fast end-to-end subset (tools/e2e_test.sh --fast).
# Prints PASS/FAIL per item and exits 1 if anything failed. Run from anywhere: tools/selftest.sh
cd "$(dirname "$0")/.." || exit 1
failed=0
log=$(mktemp)

check() {  # check <name> <command...>: run quietly, keep the output only on failure
    local name=$1; shift
    if "$@" >"$log" 2>&1; then
        printf 'PASS  %s\n' "$name"
    else
        printf 'FAIL  %s\n' "$name"; tail -n 15 "$log" | sed 's/^/      /'; failed=1
    fi
}

tsan_arena_check() {  # 1 s, rwlock and sharded; passes only if TSan reported nothing
    setarch "$(uname -m)" -R build/tests/arena_test_tsan 1 && ! grep -q "WARNING: ThreadSanitizer" "$log"
}

tape_tests() {  # core/tests/tape_test.cpp around one generator per group
    for g in arrays strings graphs; do build/tests/tape_test_$g || return 1; done
}

tsan_pool_check() {  # passes only if the check passes AND TSan reported nothing
    setarch "$(uname -m)" -R build/pool_bench_tsan --check && ! grep -q "WARNING: ThreadSanitizer" "$log"
}

check "build (tools/build.py)"                        python3 tools/build.py
check "generators match golden (golden_gen --check)"  python3 tools/golden_gen.py --check
check "fork-server edge cases (server_test)"          build/tests/server_test
check "tape session in random.h (tape_test x3)"       tape_tests
check "tape memfd via fork-server (tape_server_test)" build/tests/tape_server_test
check "checker outcome mapping (checker_test)"        build/tests/checker_test
check "C++ and Python checker mapping agree"          python3 tools/checker_agree_test.py
check "pool correctness (pool_bench --check)"         build/pool_bench --check
check "pool under ThreadSanitizer (setarch -R)"       tsan_pool_check
check "tape arena + TapeEntry pool (arena_test, 1 s)" build/tests/arena_test 1
check "arena under ThreadSanitizer (setarch -R, 1 s)" tsan_arena_check
check "aggregation self-test (aggregate --selftest)"  python3 tools/aggregate.py --selftest
check "correct solutions agree (sanity, 20 seeds)"    python3 tools/sanity.py --seeds 20 --size max
check "analysis server (e2e fast subset)"             tools/e2e_test.sh --fast

rm -f "$log"
[ "$failed" = 0 ] && echo "ALL PASS" || echo "SOME CHECKS FAILED"
exit "$failed"
