"""Problem list from Dataset/manifest.json and a cached g++ helper."""
import json, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "Dataset"
GROUPS = {"array": "arrays", "graph": "graphs", "string": "strings"}  # manifest input_type -> folder


def load():
    """Manifest entries plus: group, dir, variants (generator names present in gen/)."""
    out = []
    for p in json.loads((DATASET / "manifest.json").read_text())["problems"]:
        group = GROUPS[p["input_type"]]
        d = DATASET / "problems" / group / p["name"]
        assert d.is_dir(), d
        variants = ["generator"] + (["generator_alt_1"] if (d / "gen/generator_alt_1.cpp").exists() else [])
        out.append(dict(p, group=group, dir=d, variants=variants))
    return out


def flags(pdir, opt="-O2"):
    return [opt, "-std=c++17", "-w", "-I", str(DATASET / "common"), "-I", str(pdir), "-I", str(pdir / "gen")]


def compile(src, out, flags):
    """g++ src -> out, skipped if out is newer than src. Raises on compile error."""
    src, out = Path(src), Path(out)
    if out.exists() and out.stat().st_mtime > src.stat().st_mtime:
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["g++", *flags, "-o", str(out), str(src)], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"compile failed: {src}\n{r.stderr[-2000:]}")
    return out
