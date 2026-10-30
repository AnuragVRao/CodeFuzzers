"""Descriptive op-log analysis of results/part2 (read-only; NOT part of the kill criterion).
Per problem per mode: single-operator change rates per operator, same-value write rates per operator, and for
draw mode the size no-op split of single-op size children whose output did not change."""
import json, sys
from collections import Counter, defaultdict
import problems

R = problems.ROOT / "results" / "part2"


def mask_of(upper):
    if upper < 0:
        return 0
    if not (upper & (upper + 1)):
        return upper
    return (1 << upper.bit_length()) - 1


def rows(path):
    for line in path.read_text().splitlines()[1:]:
        f = line.split()
        ops = [o.split(":") for o in f[11:]]
        yield dict(status=int(f[5]), changed=f[8], n=int(f[10]), ops=ops)


out = {}
for d in sorted(p for p in R.iterdir() if p.is_dir()):
    out[d.name] = {}
    for mode in ("guided", "byte", "draw"):
        single = defaultdict(lambda: [0, 0])   # op -> [children, changed]
        same = defaultdict(lambda: [0, 0])     # op -> [records, old == new]
        split = Counter()
        for r in rows(d / f"{mode}.tsv"):
            for o in r["ops"]:
                op = o[0]
                old, new = (int(o[1]), int(o[2])) if op == "size" else (int(o[2]), int(o[3]))
                same[op][0] += 1
                same[op][1] += old == new
            if r["status"] != 0:
                continue
            kinds = {o[0] for o in r["ops"]}
            if r["n"] == 1:
                op = r["ops"][0][0]
                single[op][0] += 1
                single[op][1] += r["changed"] == "1"
                if mode == "draw" and op == "size" and r["changed"] == "0":
                    old, new, factor = int(r["ops"][0][1]), int(r["ops"][0][2]), float(r["ops"][0][3])
                    if factor == 1:
                        split["factor 1"] += 1
                    elif old == new:
                        split["clamp"] += 1
                    elif mask_of(old - 1) == mask_of(new - 1):
                        split["same-mask-band"] += 1
                    else:
                        split["other"] += 1
        out[d.name][mode] = dict(single={k: dict(children=v[0], change_rate=v[1] / v[0] if v[0] else None) for k, v in single.items()},
                                 same_value={k: dict(records=v[0], same_rate=v[1] / v[0] if v[0] else None) for k, v in same.items()},
                                 size_noop_split=dict(split) if mode == "draw" else None)
json.dump(out, sys.stdout, indent=1)
