# PEG vs Earley Parser Benchmark Suite

Two parsers written from scratch over one shared grammar format, plus a benchmark
and correctness harness that compares them on speed, memory, and which languages
they accept.

| Parser | Approach | Guarantees |
|---|---|---|
| `PEGParser` | Packrat: ordered choice + memoization | Linear time/space for a fixed grammar, but the language it accepts can differ from the CFG |
| `EarleyParser` | Chart parsing with Aycock-Horspool nullable handling | Any CFG (left recursion, ambiguity, epsilon rules); O(n^3) worst case |

Both return the same derivation-tree format `(symbol, [children])`, so trees can be
compared directly and fed into a grammar-based fuzzer later.

## Usage

```bash
python -m unittest -v          # 13 correctness tests
python expressiveness.py       # where PEG and CFG parsing disagree
python bench.py --quick        # fast benchmark (a few seconds)
python bench.py                # full benchmark -> results/results.csv + benchmark.png
python bench.py --memory       # also record peak memory (tracemalloc)
```

## What it measures

**Workloads**
- `expr`: arithmetic expressions, unambiguous and right-recursive. Both parsers must return identical trees (asserted).
- `json`: a JSON subset. Same identical-tree check.
- `ambiguous`: `S -> S+S | 1`. Left-recursive and ambiguous, so PEG cannot parse it and Earley can.

**Metrics:** median parse time over repeats, input length, "work" (PEG memo entries / Earley chart states), optional peak memory, and a fitted log-log growth exponent per parser.

**Expressiveness (`expressiveness.py`)**
- `PEG_SURPRISE`: as a CFG it is a^(2n); the PEG only accepts lengths 2, 4, 8, 16, 32, ...
- 1000 random grammars with one generated string each: Earley accepts 1000/1000; the PEG accepts about 55%.

## Sample results

| Workload | PEG exponent | Earley exponent | Notes |
|---|---|---|---|
| expr | ~1.2 | ~1.7 | Earley states grow superlinearly on right recursion (no Leo optimization) |
| json | ~1.3 | ~1.3 | Both near linear; Earley ~7x slower, ~25x more states |
| ambiguous | rejects | ~2.2 | PEG cannot handle left recursion |

At 6.8k chars of expression input: PEG ~40 ms (17k memo entries) vs Earley ~1 s (1.4M states).