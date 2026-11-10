#!/usr/bin/env python3
"""
Where PEG and CFG parsing disagree.

1. The PEG_SURPRISE grammar from the chapter: a^(2n) as a CFG, a^(2^k) as a PEG.
2. Differential test on random grammars: Earley must always accept strings the
   grammar generates; PEG sometimes rejects them (ordered choice commits too early).
"""
import random

import grammars as G
from parsers import EarleyParser, ParseError, PEGParser, tree_to_string


def accepts(parser, text):
    try:
        return tree_to_string(parser.parse(text)) == text
    except ParseError:
        return False


def surprise():
    peg, earley = PEGParser(G.PEG_SURPRISE), EarleyParser(G.PEG_SURPRISE)
    print("PEG_SURPRISE:  <A> -> a<A>a | aa     (CFG language: a^(2n), n >= 1)")
    print(f"  {'length':>6}  {'Earley':>7}  {'PEG':>5}")
    for n in range(1, 17):
        s = "a" * (2 * n)
        e, p = accepts(earley, s), accepts(peg, s)
        flag = "" if e == p else "   <-- PEG rejects a valid string"
        print(f"  {len(s):>6}  {str(e):>7}  {str(p):>5}{flag}")


def random_grammars(count=1000, seed=0):
    rng = random.Random(seed)
    earley_ok = peg_ok = 0
    for _ in range(count):
        g = G.make_random_grammar(rng)
        s = G.generate(g, rng)
        earley_ok += accepts(EarleyParser(g), s)
        peg_ok += accepts(PEGParser(g), s)
    print(f"\nRandom grammars ({count}), one generated string each:")
    print(f"  Earley accepted {earley_ok}/{count}  (must be all of them)")
    print(f"  PEG    accepted {peg_ok}/{count}  ({100 * peg_ok / count:.1f}%)")
    assert earley_ok == count, "Earley rejected a string its own grammar generated!"


if __name__ == "__main__":
    surprise()
    random_grammars()