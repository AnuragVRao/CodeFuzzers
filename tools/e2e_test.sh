#!/usr/bin/env bash
# End-to-end test of the analysis server (tools/server.py) on free ports with a temporary job directory:
# every example, a multipart upload (deque bug), the whole-job wall limit (CF_WALL_LIMIT_OVERRIDE_S, test-only),
# cancel, and the fork-bomb guard rail. Prints PASS/FAIL per check, exit 1 on any FAIL.
# Usage: tools/e2e_test.sh [--fast]    (--fast: only broken_compile and one upload validation error)
cd "$(dirname "$0")/.." || exit 1
FAST=0; [ "$1" = "--fast" ] && FAST=1
WORK=$(mktemp -d); failed=0; PIDS=()
trap 'kill "${PIDS[@]}" 2>/dev/null; sleep 0.5; rm -rf "$WORK"' EXIT

free_port() { python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1])'; }
start_server() {  # start_server <name> [ENV=val...] -> sets $<name>_URL and $<name>_JOBS
    local name=$1; shift; local port jobs="$WORK/jobs_$name"; port=$(free_port); mkdir -p "$jobs"
    env CF_PORT="$port" CF_JOBS_DIR="$jobs" "$@" python3 tools/server.py > "$WORK/$name.log" 2>&1 &
    PIDS+=($!)
    for _ in $(seq 50); do curl -s "http://127.0.0.1:$port/api/examples" >/dev/null && break; sleep 0.2; done
    eval "${name}_URL=http://127.0.0.1:$port; ${name}_JOBS=$jobs"
}
jget() { python3 -c "import sys,json;d=json.load(sys.stdin);print(eval(sys.argv[1]))" "$1"; }   # jget <py expr on d>
check() { if [ "$2" = 0 ]; then echo "PASS  $1"; else echo "FAIL  $1  ${3:+($3)}"; failed=1; fi; }
submit_example() { curl -s -X POST "$URL/api/examples/$1/run" | jget "d['id']"; }
wait_job() {  # wait_job <id> <timeout_s> -> prints final status JSON
    for _ in $(seq $(($2 * 5))); do
        s=$(curl -s "$URL/api/jobs/$1"); st=$(echo "$s" | jget "d['state']")
        case $st in done|failed|cancelled|timeout|interrupted) echo "$s"; return;; esac; sleep 0.2
    done; echo "$s"
}
leftovers() { ps -eo args | grep -F "$1" | grep -v "grep\|e2e_test" | wc -l; }   # processes that mention a jobs dir
expect() {  # expect <label> <status-json> <state> <summary-regex>
    local st sm; st=$(echo "$2" | jget "d['state']"); sm=$(echo "$2" | jget "d['outcome_summary']")
    [[ $st == "$3" && $sm =~ $4 ]]; check "$1 ($st: $sm)" $? "wanted $3 / $4"
}

start_server main; URL=$main_URL
E=examples/range_min_correct

if [ $FAST = 1 ]; then
    expect "broken_compile" "$(wait_job "$(submit_example broken_compile)" 60)" failed "^failed: build"
    out=$(curl -s -w ' %{http_code}' -F gen=@$E/gen.cpp -F ref=@$E/ref.cpp -F sol=@$E/sol.cpp -F budget_s=42 "$URL/api/jobs")
    [[ $out == *"budget_s must be one of"*" 400" ]]; check "upload validation: budget 42 -> 400" $? "$out"
    [ "$failed" = 0 ]; exit $((failed))
fi

# 1. every example (queued back to back, FIFO)
declare -A ID
for n in affine_point_bug lcs_bug_checker range_min_correct affine_point_seedonly broken_compile nondeterministic_gen; do ID[$n]=$(submit_example $n); done
expect "example affine_point_bug"      "$(wait_job "${ID[affine_point_bug]}" 150)" done "found after"
expect "example lcs_bug_checker"       "$(wait_job "${ID[lcs_bug_checker]}" 150)" done "found after"
expect "example range_min_correct"     "$(wait_job "${ID[range_min_correct]}" 150)" done "^clean: <"
s=$(wait_job "${ID[affine_point_seedonly]}" 150); expect "example affine_point_seedonly" "$s" done "found after"
mode=$(curl -s "$URL/api/jobs/${ID[affine_point_seedonly]}" | jget "d['report']['mode']['mode']"); [ "$mode" = seed-only ]; check "seedonly report mode is seed-only" $? "$mode"
expect "example broken_compile"        "$(wait_job "${ID[broken_compile]}" 60)" failed "^failed: build"
expect "example nondeterministic_gen"  "$(wait_job "${ID[nondeterministic_gen]}" 60)" failed "^failed: validate"

# 2. multipart upload: the dataset's deque problem (generator is already self-contained) with its planted bug
D=Dataset/problems/arrays/deque_operate_all_composite
id=$(curl -s -F gen=@$D/gen/generator.cpp -F ref=@$D/brute.cpp -F sol=@$D/sol_bug.cpp -F budget_s=60 "$URL/api/jobs" | jget "d['id']")
expect "upload deque (planted bug)" "$(wait_job "$id" 150)" done "found after"

# 4. cancel a running job
id=$(submit_example range_min_correct); sleep 8
st=$(curl -s -X POST "$URL/api/jobs/$id/cancel" | jget "d['state']"); [ "$st" = cancelled ]; check "cancel running job -> $st" $?
sleep 1; n=$(leftovers "$main_JOBS"); [ "$n" = 0 ]; check "no leftover processes after cancel" $? "$n found"

# 5. fork bomb
F=examples/_guardrails/forkbomb
id=$(curl -s -F gen=@$F/gen.cpp -F ref=@$F/ref.cpp -F sol=@$F/sol.cpp -F budget_s=60 "$URL/api/jobs" | jget "d['id']")
code=$(curl -s -m 5 -o /dev/null -w '%{http_code}' "$URL/api/jobs"); [ "$code" = 200 ]; check "server responsive during fork bomb" $? "$code"
s=$(wait_job "$id" 90); err=$(echo "$s" | jget "d['error']")
[[ $(echo "$s" | jget "d['state']") == failed && $err == "Process limit reached"* ]]; check "fork bomb -> Process limit reached message" $? "$err"
code=$(curl -s -m 5 -o /dev/null -w '%{http_code}' "$URL/api/jobs"); [ "$code" = 200 ]; check "server responsive after fork bomb" $? "$code"
sleep 1; n=$(leftovers "$main_JOBS"); [ "$n" = 0 ]; check "no leftover processes after fork bomb" $? "$n found"

# 3. whole-job wall limit (second instance, limit 5 s instead of budget + 120 s)
start_server wall CF_WALL_LIMIT_OVERRIDE_S=5; URL=$wall_URL
t0=$(date +%s.%N); id=$(submit_example range_min_correct); s=$(wait_job "$id" 30); t1=$(date +%s.%N)
el=$(python3 -c "print(round($t1 - $t0, 1))"); st=$(echo "$s" | jget "d['state']")
[[ $st == timeout ]] && python3 -c "import sys;sys.exit(0 if $el < 9 else 1)"; check "wall limit 5 s -> $st after $el s" $?
sleep 1; n=$(leftovers "$wall_JOBS"); [ "$n" = 0 ]; check "no leftover processes after timeout" $? "$n found"

[ "$failed" = 0 ] && echo "E2E: ALL PASS" || echo "E2E: SOME CHECKS FAILED"
exit $failed
