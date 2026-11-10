import random
import unittest

import grammars as G
from parsers import (EarleyParser, ParseError, PEGParser, run_with_big_stack,
                     tree_to_string)


def parses(parser, text):
    try:
        tree = parser.parse(text)
    except ParseError:
        return False
    assert tree_to_string(tree) == text
    return True


class TestParsers(unittest.TestCase):
    def test_expr_both_parse_and_trees_match(self):
        peg, earley = PEGParser(G.EXPR_GRAMMAR), EarleyParser(G.EXPR_GRAMMAR)
        for s in ["1+(2*3)", "1*(2+3.35)", "-5", "12/3.5-7", "((1))"]:
            t1, t2 = peg.parse(s), earley.parse(s)
            self.assertEqual(tree_to_string(t1), s)
            self.assertEqual(t1, t2)

    def test_invalid_input_rejected(self):
        for p in (PEGParser(G.EXPR_GRAMMAR), EarleyParser(G.EXPR_GRAMMAR)):
            for s in ["1+", "(1", "1)", "", "a", "1..2"]:
                self.assertFalse(parses(p, s), (type(p).__name__, s))

    def test_ordered_choice(self):
        g = {"<start>": ["ab", "abc"]}
        self.assertFalse(parses(PEGParser(g), "abc"))   # PEG commits to 'ab'
        self.assertTrue(parses(EarleyParser(g), "abc"))  # CFG accepts it

    def test_peg_surprise(self):
        peg, earley = PEGParser(G.PEG_SURPRISE), EarleyParser(G.PEG_SURPRISE)
        for n in range(1, 17):
            s = "a" * (2 * n)
            self.assertTrue(parses(earley, s))
            self.assertEqual(parses(peg, s), n in (1, 2, 4, 8, 16), n)

    def test_left_recursion(self):
        g = {"<start>": ["<E>"], "<E>": ["<E>+1", "1"]}
        self.assertTrue(parses(EarleyParser(g), "1+1+1"))
        self.assertFalse(parses(PEGParser(g), "1+1+1"))  # left recursion fails, no hang

    def test_ambiguous_returns_a_tree(self):
        self.assertTrue(parses(EarleyParser(G.AMBIGUOUS_GRAMMAR), "1+1+1+1+1"))

    def test_nullable(self):
        g = {"<start>": ["<A><B>c"], "<A>": ["a", ""], "<B>": ["b", ""]}
        e, p = EarleyParser(g), PEGParser(g)
        for s in ["c", "ac", "bc", "abc"]:
            self.assertTrue(parses(e, s), s)
            self.assertTrue(parses(p, s), s)
        for s in ["", "ba", "bac", "cc"]:
            self.assertFalse(parses(e, s), s)
            self.assertFalse(parses(p, s), s)

    def test_nullable_start_and_empty_input(self):
        g = {"<start>": ["<A>"], "<A>": ["a<A>", ""]}
        self.assertTrue(parses(EarleyParser(g), ""))
        self.assertTrue(parses(EarleyParser(g), "aaa"))

    def test_earley_accepts_everything_random_grammars_generate(self):
        rng = random.Random(1)
        for _ in range(300):
            g = G.make_random_grammar(rng)
            s = G.generate(g, rng)
            self.assertTrue(parses(EarleyParser(g), s), (g, s))

    def test_peg_acceptance_implies_cfg_acceptance(self):
        rng = random.Random(2)
        for _ in range(300):
            g = G.make_random_grammar(rng)
            s = G.generate(g, rng)
            if parses(PEGParser(g), s):
                self.assertTrue(parses(EarleyParser(g), s), (g, s))

    def test_json_workload(self):
        rng = random.Random(3)
        text = G.gen_json(25, rng)
        t1, t2 = PEGParser(G.JSON_GRAMMAR).parse(text), EarleyParser(G.JSON_GRAMMAR).parse(text)
        self.assertEqual(t1, t2)

    def test_long_input_with_big_stack(self):
        text = G.gen_expr(1500, random.Random(4))

        def go():
            return (PEGParser(G.EXPR_GRAMMAR).parse(text),
                    EarleyParser(G.EXPR_GRAMMAR).parse(text))

        a, b = run_with_big_stack(go)
        self.assertEqual(a, b)

    def test_timeout(self):
        text = G.gen_ambiguous(120, random.Random(0))
        with self.assertRaises(TimeoutError):
            EarleyParser(G.AMBIGUOUS_GRAMMAR).parse(text, deadline=0.0)


if __name__ == "__main__":
    unittest.main()