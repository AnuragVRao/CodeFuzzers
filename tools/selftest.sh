#!/usr/bin/env bash
# End-to-end self-test: build everything, then the golden generator hashes, the fork-server edge cases
# and checker outcome mapping (C++, and Python agreeing with it), the random.h tape session (in-process and
# through the fork-server), tape recipes (strategy guard, admitted entries replay, --op-log changes nothing),
# Part 2 (similarity unit tests, pipeline structure), the Step S shrinker (negative controls, determinism),
# the pool correctness
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

tape_strategy_check() {  # --recipes tape with an untested strategy must fail with a clear error
    local s err
    for s in global sharded snapshot random; do
        err=$(build/fuzzer --build build/majority_voting --recipes tape --strategy $s --tests 1 --out /dev/null 2>&1)
        [ $? -eq 2 ] && grep -q "needs --strategy noshare or rwlock" <<<"$err" || { echo "$s: $err"; return 1; }
    done
}

tape_smoke() {  # short tape-rwlock run on majority_voting; every admitted entry must replay (Step 2d T2)
    local d=/dev/shm/cf_selftest_tape_$$ rc
    build/fuzzer --build build/majority_voting --mode scale --strategy rwlock --recipes tape --workers 4 \
        --tests 2000 --seed 7 --out $d.json --dump-tapes $d.txt &&
        build/tests/tape_replay_check build/majority_voting $d.txt 1000000
    rc=$?
    rm -f $d.json $d.txt
    return $rc
}

oplog_run() {  # oplog_run <recipes> <name> [flags]: 1-worker majority_voting scale run, seed 7
    local d=/dev/shm/cf_selftest_oplog_$$ dump=()
    [ "$1" = tape ] && dump=(--dump-tapes "$d.$2.tapes")
    build/fuzzer --build build/majority_voting --mode scale --strategy noshare --recipes "$1" --workers 1 --tests 600 \
        --seed 7 --out "$d.$2.json" "${dump[@]}" "${@:3}"
}

oplog_check() {  # --op-log is logging only: same seed, log off vs on -> identical results; two logs identical
    local d=/dev/shm/cf_selftest_oplog_$$ rc=0 r
    for r in tape guided; do
        oplog_run $r off && oplog_run $r on1 --op-log "$d.on1.log" && oplog_run $r on2 --op-log "$d.on2.log" || { rc=1; break; }
        [ -s "$d.on1.log" ] && cmp "$d.on1.log" "$d.on2.log" || { echo "$r: op logs empty or different"; rc=1; }
        [ $r = guided ] || cmp "$d.off.tapes" "$d.on1.tapes" || { echo "$r: admitted entries differ"; rc=1; }
        python3 -c 'import json, sys
a, b = (json.load(open(f)) for f in sys.argv[1:])
res = lambda d: {k: v for k, v in d.items() if k not in ("wall_s", "tests_per_sec", "config")}
cfg = lambda d: {k: v for k, v in d["config"].items() if k not in ("out", "op_log")}
sys.exit(res(a) != res(b) or cfg(a) != cfg(b))' "$d.off.json" "$d.on1.json" || { echo "$r: results differ"; rc=1; }
        rm -f "$d".*
    done
    return $rc
}

part2_check() {  # Part 2 pipeline structure on a non-Part-2 problem, development seed 7, pass/fail only
    local d=/dev/shm/cf_selftest_part2_$$ rc
    python3 tools/part2.py --problems range_add_range_min --seed-base 7 --warmup 300 --children 50 --out "$d" --check-only
    rc=$?
    rm -rf "$d"
    return $rc
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
check "--recipes tape rejects untested strategies"    tape_strategy_check
check "tape recipes: admitted entries replay (T2)"    tape_smoke
check "--op-log changes no result (log on vs off)"    oplog_check
check "Part 2 similarity unit tests"                  python3 tools/part2.py --selftest
check "Part 2 pipeline (range_add_range_min, seed 7)" part2_check
check "shrinker: negative controls, determinism"      python3 tools/shrink_test.py --quick
check "checker outcome mapping (checker_test)"        build/tests/checker_test
check "C++ and Python checker mapping agree"          python3 tools/checker_agree_test.py
check "pool correctness (pool_bench --check)"         build/pool_bench --check
check "pool under ThreadSanitizer (setarch -R)"       tsan_pool_check
check "tape arena + TapeEntry pool (arena_test, 1 s)" build/tests/arena_test 1
check "arena under ThreadSanitizer (setarch -R, 1 s)" tsan_arena_check
check "aggregation self-test (aggregate --selftest)"  python3 tools/aggregate.py --selftest
check "paired check self-test (paired_check)"        python3 tools/paired_check.py --selftest
check "correct solutions agree (sanity, 20 seeds)"    python3 tools/sanity.py --seeds 20 --size max
check "analysis server (e2e fast subset)"             tools/e2e_test.sh --fast

rm -f "$log"
[ "$failed" = 0 ] && echo "ALL PASS" || echo "SOME CHECKS FAILED"
exit "$failed"
