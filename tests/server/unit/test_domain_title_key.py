"""Unit tests for the title comparison key.

Covers PCE-17, PCE-18 and PCE-23; REQ-029.
"""

from task_analyzer_server.domain import title_key

E_ACUTE = chr(0x00E9)
COMBINING_ACUTE = chr(0x0301)
NO_BREAK_SPACE = chr(0x00A0)
FULLWIDTH_A = chr(0xFF21)
SHARP_S = chr(0x00DF)

ACCENTED_TITLE = f"Review r{E_ACUTE}sum{E_ACUTE}"
PLAIN_TITLE = "Review resume"


def test_protected_spacing_and_case_example_compares_equal() -> None:
    assert title_key("Read notes") == title_key(" READ  NOTES ")


def test_protected_accent_example_stays_different() -> None:
    assert title_key(ACCENTED_TITLE) != title_key(PLAIN_TITLE)


def test_edge_spaces_are_trimmed() -> None:
    assert title_key("   Read notes   ") == title_key("Read notes")


def test_internal_space_runs_collapse_to_one_space() -> None:
    assert title_key("Read      notes") == title_key("Read notes")


def test_case_differences_are_folded() -> None:
    assert title_key("READ NOTES") == title_key("read notes")


def test_folding_is_unicode_case_folding_not_lowercasing() -> None:
    assert title_key(f"Stra{SHARP_S}e") == title_key("STRASSE")


def test_accents_are_retained_in_the_key() -> None:
    assert title_key(f"R{E_ACUTE}sum{E_ACUTE}") == f"r{E_ACUTE}sum{E_ACUTE}"


def test_compatibility_normalization_is_not_applied() -> None:
    assert title_key(FULLWIDTH_A) != title_key("A")


def test_no_further_equivalence_rule_is_applied() -> None:
    decomposed = f"R{'e' + COMBINING_ACUTE}sum{'e' + COMBINING_ACUTE}"

    assert title_key(f"R{E_ACUTE}sum{E_ACUTE}") != title_key(decomposed)


def test_interior_tabs_are_not_collapsed_into_spaces() -> None:
    assert title_key("Read\tnotes") != title_key("Read notes")


def test_interior_line_breaks_are_not_collapsed_into_spaces() -> None:
    assert title_key("Read\nnotes") != title_key("Read notes")


def test_runs_of_interior_tabs_are_preserved() -> None:
    assert title_key("Read\t\tnotes") != title_key("Read\tnotes")


def test_edge_tabs_are_not_trimmed() -> None:
    assert title_key("\tRead notes") != title_key("Read notes")


def test_no_break_space_is_not_a_comparison_space() -> None:
    assert title_key(f"Read{NO_BREAK_SPACE}notes") != title_key("Read notes")


def test_submitted_title_is_untouched_alongside_its_key() -> None:
    submitted = " READ  NOTES "

    key = title_key(submitted)

    assert submitted == " READ  NOTES "
    assert key == "read notes"


def test_the_key_is_already_in_key_form() -> None:
    key = title_key(" READ  NOTES ")

    assert title_key(key) == key


def test_an_unchanged_title_reproduces_its_stored_key() -> None:
    stored_key = title_key("Read notes")

    assert title_key("  Read   notes  ") == stored_key
