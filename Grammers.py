"""Grammars, scalable input generators, and a random-grammar generator."""
import random
import string
from typing import Dict, List

Grammar = Dict[str, List[str]]

DIGITS = list(string.digits)

# --- Unambiguous, right-recursive arithmetic (PEG-friendly) -----------------
EXPR_GRAMMAR: Grammar = {
    "<start>": ["<expr>"],
    "<expr>": ["<term>+<expr>", "<term>-<expr>", "<term>"],
    "<term>": ["<factor>*<term>", "<factor>/<term>", "<factor>"],
    "<factor>": ["+<factor>", "-<factor>", "(<expr>)", "<integer>.<integer>", "<integer>"],
    "<integer>": ["<digit><integer>", "<digit>"],
    "<digit>": DIGITS,
}

# --- A small JSON subset (no whitespace) ------------------------------------
JSON_GRAMMAR: Grammar = {
    "<start>": ["<value>"],
    "<value>": ["<object>", "<array>", "<string>", "<number>", "true", "false", "null"],
    "<object>": ["{<members>}", "{}"],
    "<members>": ["<pair>,<members>", "<pair>"],
    "<pair>": ["<string>:<value>"],
    "<array>": ["[<elements>]", "[]"],
    "<elements>": ["<value>,<elements>", "<value>"],
    "<string>": ['"<chars>"', '""'],
    "<chars>": ["<char><chars>", "<char>"],
    "<char>": list(string.ascii_letters + string.digits + " "),
    "<number>": ["<digits>"],
    "<digits>": ["<digit><digits>", "<digit>"],
    "<digit>": DIGITS,
}

# --- Ambiguous AND left-recursive: Earley-only territory --------------------
AMBIGUOUS_GRAMMAR: Grammar = {
    "<start>": ["<S>"],
    "<S>": ["<S>+<S>", "1"],
}

# --- The PEG surprise from the fuzzingbook chapter --------------------------
# As a CFG: a^(2n). As a PEG: only a^(2^k).
PEG_SURPRISE: Grammar = {
    "<start>": ["<A>"],
    "<A>": ["a<A>a", "aa"],
}


# --- Scalable input generators ----------------------------------------------
def gen_expr(n_terms: int, rng: random.Random) -> str:
    """Expression with n_terms operands (about 10% are parenthesized sub-exprs)."""

    def number() -> str:
        s = str(rng.randint(0, 999))
        return s + "." + str(rng.randint(0, 99)) if rng.random() < 0.2 else s

    def factor() -> str:
        if rng.random() < 0.1:
            parts = [number()]
            for _ in range(rng.randint(1, 2)):
                parts += [rng.choice("+-*/"), number()]
            return "(" + "".join(parts) + ")"
        return number()

    parts = [factor()]
    for _ in range(n_terms - 1):
        parts += [rng.choice("+-*/"), factor()]
    return "".join(parts)


def gen_json(n_items: int, rng: random.Random) -> str:
    """Array of n_items small objects with mixed values."""

    def word() -> str:
        k = rng.randint(1, 8)
        return '"' + "".join(rng.choices(string.ascii_lowercase + " ", k=k)) + '"'

    def value(depth: int = 0) -> str:
        r = rng.random()
        if r < 0.3:
            return str(rng.randint(0, 9999))
        if r < 0.6:
            return word()
        if r < 0.7:
            return rng.choice(["true", "false", "null"])
        if r < 0.85 and depth < 2:
            return "[" + ",".join(value(depth + 1) for _ in range(rng.randint(1, 3))) + "]"
        return word()

    def obj() -> str:
        return "{" + ",".join(word() + ":" + value() for _ in range(rng.randint(1, 3))) + "}"

    return "[" + ",".join(obj() for _ in range(n_items)) + "]"


def gen_ambiguous(n_terms: int, rng: random.Random) -> str:
    return "+".join(["1"] * n_terms)


# --- Random (non-recursive) grammars, like make_grammar() in the chapter ----
def make_random_grammar(rng: random.Random, num_symbols: int = 4, num_alts: int = 3,
                        alphabet: str = "ab", epsilon_prob: float = 0.1) -> Grammar:
    grammar: Grammar = {}
    names: List[str] = []
    for i in range(num_symbols):
        name = f"<N{i}>"
        alts = []
        for _ in range(num_alts):
            if rng.random() < epsilon_prob:
                alts.append("")
                continue
            items = []
            for _ in range(rng.randint(1, 4)):
                if names and rng.random() < 0.5:
                    items.append(rng.choice(names))
                else:
                    items.append(rng.choice(alphabet))
            alts.append("".join(items))
        grammar[name] = alts
        names.append(name)
    grammar["<start>"] = [names[-1]]
    return grammar


def generate(grammar: Grammar, rng: random.Random, symbol: str = "<start>") -> str:
    """Random derivation; only safe for non-recursive grammars."""
    from parsers import split_symbols  # local import avoids a cycle at load time

    out = []
    for sym in split_symbols(rng.choice(grammar[symbol])):
        out.append(generate(grammar, rng, sym) if sym in grammar else sym)
    return "".join(out)