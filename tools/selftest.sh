#!/usr/bin/env bash
# End-to-end self-test: build everything, then the fork-server edge cases, the pool correctness
# check (plain and under ThreadSanitizer, with ASLR off because GCC 13 TSan needs it), the
# aggregation self-test, and a quick correct-solution sanity run on all problems.
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

tsan_pool_check() {  # passes only if the check passes AND TSan reported nothing
    setarch "$(uname -m)" -R build/pool_bench_tsan --check && ! grep -q "WARNING: ThreadSanitizer" "$log"
}

check "build (tools/build.py)"                       python3 tools/build.py
check "fork-server edge cases (server_test)"         build/tests/server_test
check "pool correctness (pool_bench --check)"        build/pool_bench --check
check "pool under ThreadSanitizer (setarch -R)"      tsan_pool_check
check "aggregation self-test (aggregate --selftest)" python3 tools/aggregate.py --selftest
check "correct solutions agree (sanity, 20 seeds)"   python3 tools/sanity.py --seeds 20 --size max

rm -f "$log"
[ "$failed" = 0 ] && echo "ALL PASS" || echo "SOME CHECKS FAILED"
exit "$failed"
