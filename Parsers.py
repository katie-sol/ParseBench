"""
Two parsers over the same grammar format, so they can be compared fairly.

Grammar format:
    {'<start>': ['<expr>'], '<expr>': ['<term>+<expr>', '<term>'], ...}
Each expansion is a string mixing <nonterminals> and literal characters.

Both parsers return a derivation tree: (symbol, [children]).
Terminals are leaves (char, []); an empty nonterminal is (nt, []).

PEGParser    - packrat parser: ordered choice + memoization, O(n) time/space
               for a fixed grammar, but its language can differ from the CFG.
EarleyParser - handles any CFG (left recursion, ambiguity, epsilon rules),
               O(n^3) worst case. Returns ONE tree (the first derivation found)
               so the output is comparable with the PEG parser.
"""
import re
import sys
import threading
import time
from typing import Dict, List, Optional, Tuple

Tree = Tuple[str, list]
Rules = Dict[str, List[Tuple[str, ...]]]

START_SYMBOL = "<start>"
RE_NONTERMINAL = re.compile(r"(<[^<> ]*>)")


class ParseError(SyntaxError):
    """Input is not accepted by the parser."""


def is_nonterminal(symbol: str) -> bool:
    return len(symbol) > 2 and RE_NONTERMINAL.fullmatch(symbol) is not None


def split_symbols(expansion: str) -> Tuple[str, ...]:
    """'<a>+<b>' -> ('<a>', '+', '<b>'); terminals are split per character."""
    out: List[str] = []
    for part in RE_NONTERMINAL.split(expansion):
        if not part:
            continue
        if is_nonterminal(part):
            out.append(part)
        else:
            out.extend(part)
    return tuple(out)


def compile_grammar(grammar: Dict[str, List[str]]) -> Rules:
    rules = {nt: [split_symbols(e) for e in exps] for nt, exps in grammar.items()}
    for nt, alts in rules.items():
        for alt in alts:
            for sym in alt:
                if is_nonterminal(sym) and sym not in rules:
                    raise ValueError(f"{nt} uses undefined nonterminal {sym}")
    return rules


def tree_to_string(tree: Tree) -> str:
    """Concatenate the leaves of a tree (iterative, so deep trees are fine)."""
    out: List[str] = []
    stack = [tree]
    while stack:
        name, children = stack.pop()
        if children:
            stack.extend(reversed(children))
        elif not is_nonterminal(name):
            out.append(name)
    return "".join(out)


def tree_size(tree: Tree) -> int:
    count, stack = 0, [tree]
    while stack:
        _, children = stack.pop()
        count += 1
        stack.extend(children)
    return count


def run_with_big_stack(fn, stack_mb: int = 256):
    """Run fn() in a thread with a big stack (deep recursion on long inputs)."""
    result = {}

    def target():
        try:
            result["value"] = fn()
        except BaseException as exc:  # propagate to caller
            result["error"] = exc

    old_limit = sys.getrecursionlimit()
    sys.setrecursionlimit(10_000_000)
    for mb in (stack_mb, 128, 64, 32, 16):
        try:
            threading.stack_size(mb * 1024 * 1024)
            break
        except (ValueError, RuntimeError):
            continue
    t = threading.Thread(target=target)
    t.start()
    t.join()
    threading.stack_size(0)
    sys.setrecursionlimit(old_limit)
    if "error" in result:
        raise result["error"]
    return result.get("value")


class Parser:
    def __init__(self, grammar: Dict[str, List[str]], start: str = START_SYMBOL):
        self.rules = compile_grammar(grammar)
        self.start = start
        self.work = 0  # memo entries (PEG) or Earley states; set by parse()

    def parse(self, text: str, deadline: Optional[float] = None) -> Tree:
        """Parse text; raise ParseError if rejected, TimeoutError past deadline
        (deadline is a time.perf_counter() value)."""
        raise NotImplementedError


class PEGParser(Parser):
    """Packrat parser.

    Memoizes (nonterminal, position) -> (end, tree) or failure, so each pair is
    computed once. Alternatives are tried in order and the first success wins
    (no backtracking into a successful choice). Direct/indirect left recursion
    is treated as failure instead of looping forever.
    """

    def parse(self, text: str, deadline: Optional[float] = None) -> Tree:
        rules, n = self.rules, len(text)
        memo: Dict[Tuple[str, int], Optional[Tuple[int, Tree]]] = {}
        calls = 0

        def parse_nt(nt: str, pos: int):
            nonlocal calls
            key = (nt, pos)
            if key in memo:
                return memo[key]
            calls += 1
            if deadline is not None and calls & 0xFFF == 0 and time.perf_counter() > deadline:
                raise TimeoutError
            memo[key] = None  # in-progress marker: blocks left recursion
            for rule in rules[nt]:
                p, children = pos, []
                for sym in rule:
                    if sym in rules:
                        r = parse_nt(sym, p)
                        if r is None:
                            break
                        p, child = r
                        children.append(child)
                    elif p < n and text[p] == sym:
                        children.append((sym, []))
                        p += 1
                    else:
                        break
                else:  # whole rule matched -> ordered choice commits
                    result = (p, (nt, children))
                    memo[key] = result
                    return result
            return None

        try:
            res = parse_nt(self.start, 0)
        finally:
            self.work = len(memo)
        if res is None:
            raise ParseError("PEG: no match at 0")
        end, tree = res
        if end != n:
            raise ParseError(f"PEG: matched prefix of length {end}, rest {text[end:end + 10]!r}")
        return tree


class EarleyParser(Parser):
    """Earley parser with the Aycock-Horspool fix for nullable nonterminals.

    A state is (nonterminal, rule_index, dot, origin). Each chart entry stores
    one back-pointer, from which a single derivation tree is rebuilt.
    """

    def __init__(self, grammar, start: str = START_SYMBOL):
        super().__init__(grammar, start)
        # nullable nonterminal -> index of a rule that derives epsilon
        self.nullable: Dict[str, int] = {}
        changed = True
        while changed:
            changed = False
            for nt, alts in self.rules.items():
                if nt in self.nullable:
                    continue
                for i, rule in enumerate(alts):
                    if all(s in self.nullable for s in rule):
                        self.nullable[nt] = i
                        changed = True
                        break

    def _null_tree(self, nt: str) -> Tree:
        rule = self.rules[nt][self.nullable[nt]]
        return (nt, [self._null_tree(s) for s in rule])

    def parse(self, text: str, deadline: Optional[float] = None) -> Tree:
        rules, nullable, start = self.rules, self.nullable, self.start
        n = len(text)
        chart: List[dict] = [dict() for _ in range(n + 1)]   # state -> back-pointer
        order: List[list] = [[] for _ in range(n + 1)]       # states in insertion order
        waiting: List[dict] = [dict() for _ in range(n + 1)]  # nt -> states awaiting it

        for ridx in range(len(rules[start])):
            s = (start, ridx, 0, 0)
            chart[0][s] = None
            order[0].append(s)

        try:
            for k in range(n + 1):
                if deadline is not None and time.perf_counter() > deadline:
                    raise TimeoutError
                c, ordr, wait = chart[k], order[k], waiting[k]
                predicted = set()
                i = 0
                while i < len(ordr):
                    state = ordr[i]
                    i += 1
                    nt, ridx, dot, origin = state
                    rule = rules[nt][ridx]
                    if dot == len(rule):  # complete
                        for prev in waiting[origin].get(nt, ()):
                            new = (prev[0], prev[1], prev[2] + 1, prev[3])
                            if new not in c:
                                c[new] = (prev, "c", state)
                                ordr.append(new)
                        continue
                    sym = rule[dot]
                    if sym in rules:  # predict
                        wait.setdefault(sym, []).append(state)
                        if sym not in predicted:
                            predicted.add(sym)
                            for j in range(len(rules[sym])):
                                new = (sym, j, 0, k)
                                if new not in c:
                                    c[new] = None
                                    ordr.append(new)
                        if sym in nullable:  # Aycock-Horspool: skip nullable symbol
                            new = (nt, ridx, dot + 1, origin)
                            if new not in c:
                                c[new] = (state, "n", sym)
                                ordr.append(new)
                    elif k < n and text[k] == sym:  # scan
                        new = (nt, ridx, dot + 1, origin)
                        nxt = chart[k + 1]
                        if new not in nxt:
                            nxt[new] = (state, "s", sym)
                            order[k + 1].append(new)
                if k < n and not chart[k + 1]:
                    raise ParseError(f"Earley: unexpected {text[k]!r} at position {k}")
        finally:
            self.work = sum(len(c) for c in chart)

        final = None
        for ridx, rule in enumerate(rules[start]):
            s = (start, ridx, len(rule), 0)
            if s in chart[n]:
                final = s
                break
        if final is None:
            raise ParseError("Earley: unexpected end of input")

        def build(state, k) -> Tree:
            children, cur, pos = [], state, k
            while cur[2] > 0:
                prev, kind, payload = chart[pos][cur]
                if kind == "s":
                    children.append((payload, []))
                    pos -= 1
                elif kind == "c":
                    children.append(build(payload, pos))
                    pos = payload[3]
                else:
                    children.append(self._null_tree(payload))
                cur = prev
            children.reverse()
            return (cur[0], children)

        return build(final, n)