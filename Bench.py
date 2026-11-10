#!/usr/bin/env python3
"""
PEG (packrat) vs Earley benchmark.

    python bench.py                 # full run
    python bench.py --quick         # small sizes, ~seconds
    python bench.py --memory        # also record peak memory (slower)
    python bench.py --workloads expr json --repeats 5 --timeout 30

Writes results/results.csv and results/benchmark.png.
"""
import argparse
import csv
import math
import os
import random
import statistics
import time
import tracemalloc
from dataclasses import dataclass
from typing import Callable, List

import grammars as G
from parsers import (EarleyParser, ParseError, PEGParser, run_with_big_stack,
                     tree_to_string)


@dataclass
class Workload:
    description: str
    grammar: dict
    gen: Callable
    sizes: List[int]
    unambiguous: bool  # if True, both parsers must return identical trees


WORKLOADS = {
    "expr": Workload("Arithmetic expressions (unambiguous, right-recursive)",
                     G.EXPR_GRAMMAR, G.gen_expr,
                     [10, 20, 40, 80, 160, 320, 640, 1280], True),
    "json": Workload("JSON subset (unambiguous)",
                     G.JSON_GRAMMAR, G.gen_json,
                     [5, 10, 20, 40, 80, 160, 320, 640], True),
    "ambiguous": Workload("Ambiguous + left-recursive: S -> S+S | 1 (PEG cannot parse)",
                          G.AMBIGUOUS_GRAMMAR, G.gen_ambiguous,
                          [4, 8, 16, 32, 64, 96], False),
}


def measure(parser, text, repeats, timeout, memory):
    """Return (status, median_seconds, work, tree, peak_kb)."""
    times, tree, status, work = [], None, "ok", 0
    for _ in range(repeats):
        t0 = time.perf_counter()
        try:
            tree = parser.parse(text, deadline=t0 + timeout)
            status = "ok"
        except ParseError:
            tree, status = None, "rejected"
        except TimeoutError:
            return "timeout", None, parser.work, None, None
        elapsed = time.perf_counter() - t0
        times.append(elapsed)
        work = parser.work
        if elapsed > 2.0:  # don't repeat slow cases
            break
    peak = None
    if memory:
        tracemalloc.start()
        try:
            parser.parse(text, deadline=time.perf_counter() + timeout * 3)
        except (ParseError, TimeoutError):
            pass
        peak = tracemalloc.get_traced_memory()[1] / 1024
        tracemalloc.stop()
    return status, statistics.median(times), work, tree, peak


def fit_exponent(points):
    """Slope of log(time) vs log(len): empirical growth exponent."""
    pts = [(math.log(x), math.log(y)) for x, y in points if x > 0 and y > 0]
    if len(pts) < 3:
        return None
    mx = sum(p[0] for p in pts) / len(pts)
    my = sum(p[1] for p in pts) / len(pts)
    den = sum((p[0] - mx) ** 2 for p in pts)
    return sum((p[0] - mx) * (p[1] - my) for p in pts) / den if den else None


def run(args):
    rows = []
    for wname in args.workloads:
        w = WORKLOADS[wname]
        print(f"\n== {wname}: {w.description}")
        parsers = {"PEG": PEGParser(w.grammar), "Earley": EarleyParser(w.grammar)}
        dead = set()
        sizes = w.sizes[:5] if args.quick else w.sizes
        for size in sizes:
            text = w.gen(size, random.Random(f"{args.seed}-{wname}-{size}"))
            trees = {}
            for pname, parser in parsers.items():
                if pname in dead:
                    continue
                status, t, work, tree, peak = measure(
                    parser, text, args.repeats, args.timeout, args.memory)
                if status == "timeout":
                    dead.add(pname)
                if tree is not None:
                    assert tree_to_string(tree) == text, f"{pname} tree does not round-trip"
                    trees[pname] = tree
                rows.append(dict(workload=wname, parser=pname, size=size,
                                 input_len=len(text), status=status,
                                 time_s=t if t is not None else "",
                                 work=work if work is not None else "",
                                 peak_kb=f"{peak:.0f}" if peak is not None else ""))
                ts = f"{t * 1000:10.2f} ms" if t is not None else "   (timeout)  "
                print(f"  {pname:6} n={size:<5} len={len(text):<7} {status:9} {ts}  work={work}")
            if w.unambiguous and len(trees) == 2:
                assert trees["PEG"] == trees["Earley"], "parsers disagree on an unambiguous grammar"
    return rows


def summarize(rows):
    print("\n== Empirical growth exponent (time ~ len^k, last 5 accepted sizes)")
    print(f"  {'workload':10} {'parser':7} {'k':>6}   status")
    for wname in dict.fromkeys(r["workload"] for r in rows):
        for pname in ("PEG", "Earley"):
            mine = [r for r in rows if r["workload"] == wname and r["parser"] == pname]
            ok = [(r["input_len"], r["time_s"]) for r in mine if r["status"] == "ok"][-5:]
            k = fit_exponent(ok)
            note = "" if ok else "/".join(sorted({r["status"] for r in mine}))
            print(f"  {wname:10} {pname:7} {k if k is None else round(k, 2)!s:>6}   {note}")


def write_outputs(rows, out_dir, plot):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "results.csv")
    with open(path, "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)
    print(f"\nWrote {path}")
    if not plot:
        return
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed; skipping plot (pip install matplotlib)")
        return
    names = list(dict.fromkeys(r["workload"] for r in rows))
    fig, axes = plt.subplots(1, len(names), figsize=(5.2 * len(names), 4.2), squeeze=False)
    for ax, wname in zip(axes[0], names):
        for pname, style in (("PEG", "o-"), ("Earley", "s--")):
            pts = [(r["input_len"], r["time_s"]) for r in rows
                   if r["workload"] == wname and r["parser"] == pname and r["status"] == "ok"]
            if pts:
                ax.loglog(*zip(*pts), style, label=pname)
        ax.set_title(wname)
        ax.set_xlabel("input length (chars)")
        ax.set_ylabel("parse time (s)")
        ax.grid(True, which="both", alpha=0.3)
        ax.legend()
    fig.tight_layout()
    png = os.path.join(out_dir, "benchmark.png")
    fig.savefig(png, dpi=150)
    print(f"Wrote {png}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--workloads", nargs="+", default=list(WORKLOADS), choices=list(WORKLOADS))
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--timeout", type=float, default=20.0, help="seconds per parse")
    ap.add_argument("--quick", action="store_true", help="only the 5 smallest sizes")
    ap.add_argument("--memory", action="store_true", help="record peak memory via tracemalloc")
    ap.add_argument("--seed", default="0")
    ap.add_argument("--out", default="results")
    ap.add_argument("--no-plot", action="store_true")
    args = ap.parse_args()

    rows = run_with_big_stack(lambda: run(args))
    summarize(rows)
    write_outputs(rows, args.out, not args.no_plot)


if __name__ == "__main__":
    main()