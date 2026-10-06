"""
Deterministic checks for the CV bullet rules
(knowledge_base/instructions/cv_bullet_generation_v1.json). Pure functions.

Each violation carries the key of the rule it breaks (a key of the file's
`validation_rules`), so it points straight back at the rules file. Only the
checks the file lists under `check_types.deterministic` are here. The LLM/hybrid
ones (result shown, domain named, buzzword share, simple language, ...) are not.

Which checks apply to which edit is the caller's decision:
  check_line         what ONE bullet has to satisfy (word limit, opening word,
                     pronouns, digits, one sentence)
  check_description  those per-line checks on every line, PLUS the checks that only
                     make sense for a whole 5-line project description (line count,
                     unique opening words, numeral counts, progression on line 4)

The opening-word list in the rules file is the whole vocabulary this module
accepts: a verb that is not in `recommended_words` is reported. Extend the file to
accept more.

    from utils.bullet_rules import check_line, check_description
    check_line("Built a churn model on 40K rows, lifting recall from 62% to 71% in 3 weeks.")
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

import config

RULES_FILE = config.KB_DIR / "instructions" / "cv_bullet_generation_v1.json"


@dataclass(frozen=True)
class Violation:
    rule: str                       # a key of validation_rules in the rules file
    detail: str
    line_index: Optional[int] = None  # 0-based line within a description; None for a single line


@lru_cache(maxsize=1)
def load_rules(path: Path = RULES_FILE) -> dict:
    # in : path = the rules JSON
    # out: the parsed rules. Cached, so an edit to the file needs a restart (or load_rules.cache_clear()).
    return json.loads(Path(path).read_text(encoding="utf-8"))


# --- small text helpers -------------------------------------------------------

_MARKER = re.compile(r"^[\s•●▪◦‣∙*\-–—]+")
_NUMERAL = re.compile(r"\d+(?:[.,]\d+)*")
# one sentence per line. A '.', '!' or '?' followed by a space and a capital is a second
# sentence; decimals ("0.62") and lowercase continuations ("e.g. spark") are not.
_SENTENCE_BREAK = re.compile(r"[.!?]\s+[A-Z]")
# "from 62% to 89%", "from 0.62 to 0.68", "5 hours to 20 minutes", "62% -> 89%"
_PROGRESSION = re.compile(
    r"\bfrom\b[^;]*?\d[^;]*?\bto\b[^;]*?\d|\d[\w%$.,]*\s*(?:to|→|->)\s*\$?\d", re.I
)
_NUMBER_WORDS = {
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
    "eighteen", "nineteen", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
    "eighty", "ninety", "hundred", "thousand", "million", "billion",
}
# irregular past tenses that the suffix rules in _stem cannot reach
_IRREGULAR = {"built": "build", "led": "lead", "ran": "run", "wrote": "write", "drove": "drive",
              "grew": "grow", "won": "win", "chose": "choose", "made": "make", "took": "take"}


def count_words(line: str) -> int:
    # The file's counting rule: a word is a token separated by whitespace, so
    # "stock-out", "40%" and "$85K" each count as one.
    return len(line.split())


def first_word(line: str) -> str:
    # in : a bullet, with or without a leading marker ("• Built ...")
    # out: its first word without surrounding punctuation ("" for an empty line)
    tokens = _MARKER.sub("", line).split()
    return re.sub(r"^\W+|\W+$", "", tokens[0]) if tokens else ""


def _tokens(line: str) -> list[str]:
    return [t for t in (re.sub(r"^\W+|\W+$", "", raw) for raw in line.split()) if t]


def _stem(word: str) -> str:
    # Rough verb root, enough to see that Build/Built or Reduce/Reduced/Reducing share one.
    w = re.sub(r"[^a-z]", "", word.lower())
    w = _IRREGULAR.get(w, w)
    if w.endswith("ied") and len(w) > 4:
        w = w[:-3] + "y"
    elif w.endswith("ing") and len(w) > 5:
        w = w[:-3]
    elif w.endswith("ed") and len(w) > 4:
        w = w[:-2]
    elif w.endswith("es") and len(w) > 4:
        w = w[:-2]
    elif w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        w = w[:-1]
    if w.endswith("e") and len(w) > 3:
        w = w[:-1]
    return w


def _is_number_word(token: str) -> bool:
    # "twenty" and "twenty-five" are spelled-out numbers; "one-hot" is not (every part must be one).
    parts = token.lower().split("-")
    return all(p in _NUMBER_WORDS for p in parts)


# --- per-line checks ----------------------------------------------------------

def check_line(line: str, rules: Optional[dict] = None, line_index: Optional[int] = None) -> list[Violation]:
    # in : line = one bullet, rules = the parsed rules (default: the rules file), line_index = its position if known
    # out: every deterministic rule this bullet breaks (empty = clean)
    r = rules or load_rules()
    out: list[Violation] = []

    def bad(rule: str, detail: str) -> None:
        out.append(Violation(rule, detail, line_index))

    limit = r["structure"]["line_1"]["word_limit"]       # the same 15-18 on every line
    n = count_words(line)
    if not limit["min"] <= n <= limit["max"]:
        bad("all_lines_within_word_limit", f"{n} words, allowed {limit['min']}-{limit['max']}")

    words = r["action_word_rules"]
    opener = first_word(line)
    if opener.lower() in {w.lower() for w in words["discouraged_words"]}:
        bad("no_discouraged_action_words", f"opens with the discouraged word {opener!r}")
    elif opener.lower() not in {w.lower() for w in words["recommended_words"]}:
        bad("all_lines_start_with_action_word", f"{opener!r} is not in the action-word list")

    tokens = _tokens(line)
    forbidden = {w.lower() for w in r["global_rules"]["voice"]["forbidden_words"] if w != "I"}
    pronouns = [t for t in tokens if t == "I" or (t.lower() in forbidden and not t.isupper())]
    if pronouns:                                          # "US" (all caps) is a country, not 'us'
        bad("no_first_person_pronouns", f"first-person word(s): {sorted(set(pronouns))}")

    spelled = [t for t in tokens if _is_number_word(t)]
    if spelled:
        bad("numerals_written_as_digits", f"number(s) spelled out: {sorted(set(spelled))}")

    if _SENTENCE_BREAK.search(line):
        bad("each_line_is_single_sentence", "more than one sentence")
    return out


def describe_line_rules(rules: Optional[dict] = None) -> str:
    # The per-line rules in plain words, for a writer prompt. Built from the rules file, so the
    # text the model reads and what check_line enforces cannot drift apart.
    # in : rules = the parsed rules (default: the rules file)
    # out: a block of text listing what every rewritten line must satisfy
    r = rules or load_rules()
    limit = r["structure"]["line_1"]["word_limit"]
    words = r["action_word_rules"]
    forbidden = ", ".join(r["global_rules"]["voice"]["forbidden_words"])
    return "\n".join([
        "LINE RULES (every rewritten line must satisfy all of them):",
        f"- {limit['min']}-{limit['max']} words. A hyphenated word or a figure such as 40% or $85K counts as one word.",
        f"- Open with one of these past-tense action words: {', '.join(words['recommended_words'])}.",
        f"- Never open with: {', '.join(words['discouraged_words'])}.",
        f"- No first-person words ({forbidden}). Write a subjectless action statement.",
        "- Write numbers as digits, never as words.",
        "- One sentence only.",
    ])


# --- whole-description checks -------------------------------------------------

def check_description(lines: list[str], rules: Optional[dict] = None) -> list[Violation]:
    # in : lines = the bullets of one project description, in order
    # out: every per-line violation, plus the set-level ones (empty = clean)
    r = rules or load_rules()
    out: list[Violation] = []
    for i, line in enumerate(lines):
        out += check_line(line, r, i)

    def bad(rule: str, detail: str, index: Optional[int] = None) -> None:
        out.append(Violation(rule, detail, index))

    want = r["validation_rules"]["exact_line_count"]
    if len(lines) != want:
        bad("exact_line_count", f"{len(lines)} lines, expected {want}")

    openers = [first_word(line).lower() for line in lines]
    for i, word in enumerate(openers):
        if word and word in openers[:i]:
            bad("no_action_word_repetition", f"{word!r} already opens an earlier line", i)

    for i, word in enumerate(openers):
        stem = _stem(word)
        if len(stem) < 4:
            continue
        for j, other in enumerate(lines):
            if j == i or openers[j] == word:              # identical openers are reported above
                continue
            if any(_stem(t) == stem for t in _tokens(other)):
                bad("no_action_word_root_repetition",
                    f"line {i + 1} opens with {word!r} and line {j + 1} uses the same root", i)
                break

    numerals = sum(len(_NUMERAL.findall(line)) for line in lines)
    need = r["validation_rules"]["minimum_numeric_mentions"]
    if numerals < need:
        bad("minimum_numeric_mentions", f"{numerals} numerals, at least {need} needed")

    if len(lines) >= 4 and not _PROGRESSION.search(lines[3]):
        bad("line_4_has_numerical_progression", "no before/after numbers (from X to Y)", 3)
    if len(lines) >= 5 and not _NUMERAL.search(lines[4]):
        bad("line_5_has_final_numerical_metric", "no number in the final-result line", 4)
    return out
