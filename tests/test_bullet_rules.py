"""
The deterministic CV bullet-rule checks (utils/bullet_rules.py), run against the
real rules file. Limits and word lists are read from the file, not hard-coded
here, so editing the rules does not break these tests unless the rule logic does.
"""

from __future__ import annotations

import pytest

from utils.bullet_rules import check_description, check_line, count_words, first_word, load_rules

RULES = load_rules()
OPENER = RULES["action_word_rules"]["recommended_words"][0]          # e.g. "Engineered"
DISCOURAGED = RULES["action_word_rules"]["discouraged_words"][0]     # e.g. "Worked"
LIMIT = RULES["structure"]["line_1"]["word_limit"]
GOOD = f"{OPENER} " + " ".join(["plain"] * (LIMIT["min"] - 1))       # exactly the minimum length


def _rules_hit(violations):
    return {v.rule for v in violations}


def test_the_rules_files_own_example_passes_every_check():
    assert check_description(RULES["example"]["lines"]) == []


def test_a_minimal_good_line_is_clean():
    assert count_words(GOOD) == LIMIT["min"]
    assert check_line(GOOD) == []


def test_word_limit_both_ends():
    too_short = f"{OPENER} " + " ".join(["plain"] * (LIMIT["min"] - 2))
    too_long = f"{OPENER} " + " ".join(["plain"] * LIMIT["max"])
    assert _rules_hit(check_line(too_short)) == {"all_lines_within_word_limit"}
    assert _rules_hit(check_line(too_long)) == {"all_lines_within_word_limit"}
    assert check_line(f"{OPENER} " + " ".join(["plain"] * (LIMIT["max"] - 1))) == []


def test_hyphenated_words_and_figures_count_once():
    assert count_words("cut stock-out rate by 40% to $85K") == 7


def test_opening_word_rules():
    assert _rules_hit(check_line(GOOD.replace(OPENER, DISCOURAGED, 1))) == {"no_discouraged_action_words"}
    assert _rules_hit(check_line(GOOD.replace(OPENER, "Pondered", 1))) == {"all_lines_start_with_action_word"}
    assert check_line(GOOD.replace(OPENER, OPENER.lower(), 1)) == []     # case-insensitive
    assert check_line("• " + GOOD) == []                                  # a list marker is not a word
    assert first_word("• Built a thing") == "Built"
    assert first_word("") == ""


def test_first_person_pronouns():
    with_we = GOOD + " our"
    hit = check_line(with_we.replace("plain plain", "plain we", 1))
    assert "no_first_person_pronouns" in _rules_hit(hit)
    assert "no_first_person_pronouns" in _rules_hit(check_line(GOOD.replace("plain plain", "plain me", 1)))


def test_us_the_country_is_not_a_pronoun():
    assert "no_first_person_pronouns" not in _rules_hit(check_line(GOOD.replace("plain plain", "US market", 1)))


def test_spelled_out_numbers():
    assert "numerals_written_as_digits" in _rules_hit(check_line(GOOD.replace("plain plain", "twenty percent", 1)))
    assert "numerals_written_as_digits" in _rules_hit(check_line(GOOD.replace("plain plain", "twenty-five", 1)))
    assert "numerals_written_as_digits" not in _rules_hit(check_line(GOOD.replace("plain plain", "one-hot encoding", 1)))


def test_one_sentence_per_line():
    assert "each_line_is_single_sentence" in _rules_hit(check_line(GOOD.replace("plain plain", "plain. Then", 1)))
    assert "each_line_is_single_sentence" not in _rules_hit(check_line(GOOD.replace("plain plain", "0.62 to 0.68", 1)))
    assert "each_line_is_single_sentence" not in _rules_hit(check_line(GOOD + "."))


def test_violations_carry_the_line_index():
    lines = RULES["example"]["lines"][:4] + ["short"]
    assert {v.line_index for v in check_description(lines) if v.rule == "all_lines_within_word_limit"} == {4}


# --- whole-description checks ----------------------------------------------------

def _example():
    return list(RULES["example"]["lines"])


def test_line_count_must_be_exact():
    assert "exact_line_count" in _rules_hit(check_description(_example()[:4]))
    assert "exact_line_count" in _rules_hit(check_description(_example() + [_example()[0]]))


def test_repeated_opening_word():
    lines = _example()
    lines[1] = lines[1].replace("Built", "Addressed", 1)
    hit = [v for v in check_description(lines) if v.rule == "no_action_word_repetition"]
    assert [v.line_index for v in hit] == [1]


@pytest.mark.parametrize("first,second", [("Built", "Build"), ("Reduced", "Reduce"), ("Optimized", "Optimize")])
def test_same_root_in_another_form(first, second):
    lines = _example()
    lines[0] = lines[0].replace("Addressed", first, 1)
    lines[2] = lines[2].replace("Applied", second, 1)
    assert "no_action_word_root_repetition" in _rules_hit(check_description(lines))


def test_an_opening_word_reused_as_a_verb_elsewhere():
    lines = _example()
    lines[4] = lines[4].replace("saving an estimated", "building an estimated", 1)     # Built (line 2) vs building
    assert "no_action_word_root_repetition" in _rules_hit(check_description(lines))


def test_numeral_count_progression_and_final_metric():
    no_numbers = [l for l in _example()]
    for i, line in enumerate(no_numbers):
        no_numbers[i] = "".join(c for c in line if not c.isdigit())
    hit = _rules_hit(check_description(no_numbers))
    assert {"minimum_numeric_mentions", "line_4_has_numerical_progression",
            "line_5_has_final_numerical_metric"} <= hit
    only_line5 = _example()
    only_line5[3] = ("Automated nightly data cleaning across 12 sources, shrinking manual preparation "
                     "time sharply and keeping every analyst report fresh.")
    assert _rules_hit(check_description(only_line5)) == {"line_4_has_numerical_progression"}
