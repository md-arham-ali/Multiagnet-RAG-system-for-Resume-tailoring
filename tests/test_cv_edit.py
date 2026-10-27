"""
The Document agent's tree mechanics (utils/cv_handling/cv_edit.py): apply
edits, list what changed, render Markdown. Pure code on a hand-built tree - no
PDF, no model, no files.
"""

from __future__ import annotations

import pytest

from state.state import CVNode, CVTree, Edit, EditAction, EditPurpose, NodeKind, SectionType
from utils.cv_handling.cv_edit import apply_edits, changed_lines, index_nodes, render_markdown


def _n(node_id, kind, stype, depth, parent, text="", title="", attrs=None, children=None):
    return CVNode(node_id=node_id, kind=kind, section_type=stype, depth=depth, parent_id=parent,
                  title=title, text=text, raw_text=text, attrs=attrs or {}, children=children or [])


def _tree() -> CVTree:
    E, X, P, S, C, H = (SectionType.EXPERIENCE, SectionType.EDUCATION, SectionType.PROJECTS,
                        SectionType.SKILLS, SectionType.COURSEWORK, SectionType.HEADER)
    header = _n("header", NodeKind.SECTION, H, 1, "cv", "Header", "Header", children=[
        _n("header.i0", NodeKind.ITEM, H, 2, "header", "[Name]"),
        _n("header.i1", NodeKind.ITEM, H, 2, "header", "a@b.c | github"),
    ])
    experience = _n("experience", NodeKind.SECTION, E, 1, "cv", "Experience", "Experience", children=[
        _n("experience.0", NodeKind.ENTRY, E, 2, "experience", "Engineer | Acme | 2020 – 2022", "Engineer", children=[
            _n("experience.0.b0", NodeKind.BULLET, E, 3, "experience.0", "Built a pipeline"),
            _n("experience.0.b1", NodeKind.BULLET, E, 3, "experience.0", "Cut costs by 20%"),
        ]),
    ])
    projects = _n("projects", NodeKind.SECTION, P, 1, "cv", "Projects", "Projects", children=[
        _n("projects.0", NodeKind.ENTRY, P, 2, "projects", "Churn Model | XGBoost", "Churn Model", children=[
            _n("projects.0.b0", NodeKind.BULLET, P, 3, "projects.0", "Predicted churn"),
        ]),
    ])
    skills = _n("skills", NodeKind.SECTION, S, 1, "cv", "Technical Skills", "Technical Skills", children=[
        _n("skills.0", NodeKind.ENTRY, S, 2, "skills", "Languages: stale joined text", "Languages",
           attrs={"group": "Languages"}, children=[
               _n("skills.0.i0", NodeKind.ITEM, S, 3, "skills.0", "Python (Pandas, NumPy)"),
               _n("skills.0.i1", NodeKind.ITEM, S, 3, "skills.0", "SQL"),
           ]),
    ])
    courses = _n("coursework", NodeKind.SECTION, C, 1, "cv", "Courseworks", "Courseworks", children=[
        _n("coursework.i0", NodeKind.ITEM, C, 2, "coursework", "Databases"),
    ])
    root = _n("cv", NodeKind.CV, SectionType.OTHER, 0, None, title="cv.pdf",
              children=[header, experience, projects, skills, courses])
    return CVTree(source_file="cv.pdf", root=root)


def _edit(target, text="New text", action=EditAction.REPLACE):
    return Edit(target_id=target, action=action, new_text=text, purpose=EditPurpose.QUANTIFIES)


# --- apply_edits ----------------------------------------------------------------

def test_replace_changes_only_the_target_and_never_the_original():
    tree = _tree()
    new = apply_edits(tree, [_edit("experience.0.b1", "Cut cloud costs by 20% in 3 months")])
    assert index_nodes(new)["experience.0.b1"].text == "Cut cloud costs by 20% in 3 months"
    assert index_nodes(tree)["experience.0.b1"].text == "Cut costs by 20%"       # original untouched
    assert index_nodes(new)["experience.0.b0"].text == "Built a pipeline"        # neighbours untouched
    assert index_nodes(new)["experience.0.b1"].raw_text == "Cut costs by 20%"    # PDF text kept for audit
    assert new is not tree


def test_new_text_whitespace_is_normalised():
    new = apply_edits(_tree(), [_edit("projects.0.b0", "  Predicted   churn \n  for 3 segments ")])
    assert index_nodes(new)["projects.0.b0"].text == "Predicted churn for 3 segments"


def test_an_empty_patch_set_returns_an_equal_copy():
    tree = _tree()
    new = apply_edits(tree, [])
    assert new is not tree and new == tree


def test_unknown_target_is_loud():
    with pytest.raises(KeyError, match="nope.9"):
        apply_edits(_tree(), [_edit("nope.9")])


@pytest.mark.parametrize("target", ["cv", "experience", "experience.0", "skills.0"])
def test_structure_nodes_cannot_take_new_text(target):
    with pytest.raises(ValueError, match="only a bullet or an item"):
        apply_edits(_tree(), [_edit(target)])


@pytest.mark.parametrize("action", [EditAction.INSERT, EditAction.DROP])
def test_only_replace_is_supported_for_now(action):
    with pytest.raises(NotImplementedError):
        apply_edits(_tree(), [_edit("experience.0.b0", action=action)])


@pytest.mark.parametrize("text", [None, "", "   \n "])
def test_empty_new_text_is_loud(text):
    with pytest.raises(ValueError, match="no new_text"):
        apply_edits(_tree(), [_edit("experience.0.b0", text)])


def test_two_edits_on_one_line_are_loud():
    with pytest.raises(ValueError, match="two edits"):
        apply_edits(_tree(), [_edit("experience.0.b0", "A"), _edit("experience.0.b0", "B")])


# --- changed_lines --------------------------------------------------------------

def test_changed_lines_lists_only_edited_nodes_in_tree_order():
    tree = _tree()
    new = apply_edits(tree, [_edit("projects.0.b0", "P2"), _edit("experience.0.b0", "E2")])
    changes = changed_lines(tree, new)
    assert [c.node_id for c in changes] == ["experience.0.b0", "projects.0.b0"]
    assert (changes[0].before, changes[0].after) == ("Built a pipeline", "E2")


def test_identical_trees_have_no_changes():
    assert changed_lines(_tree(), _tree()) == []


def test_a_node_in_only_one_tree_counts_as_a_change():
    old, new = _tree(), _tree()
    index_nodes(new)["projects.0"].children.pop()            # drop projects.0.b0 from the new tree
    assert [(c.node_id, c.before, c.after) for c in changed_lines(old, new)] == [
        ("projects.0.b0", "Predicted churn", "")
    ]


# --- render_markdown --------------------------------------------------------------

def test_markdown_structure_and_order():
    md = render_markdown(_tree())
    lines = md.splitlines()
    assert lines[0] == "# [Name]"
    assert "a@b.c | github" in md
    order = [md.index(h) for h in ("## Experience", "## Projects", "## Technical Skills", "## Courseworks")]
    assert order == sorted(order)
    assert "### Engineer | Acme | 2020 – 2022\n- Built a pipeline\n- Cut costs by 20%" in md
    assert "### Churn Model | XGBoost\n- Predicted churn" in md
    assert "## Courseworks\n\n- Databases" in md
    assert md.endswith("\n") and not md.endswith("\n\n")


def test_skills_group_is_rebuilt_from_its_items():
    tree = _tree()
    new = apply_edits(tree, [_edit("skills.0.i1", "PostgreSQL")])
    assert "- **Languages:** Python (Pandas, NumPy) | SQL" in render_markdown(tree)
    assert "- **Languages:** Python (Pandas, NumPy) | PostgreSQL" in render_markdown(new)
    assert "stale joined text" not in render_markdown(new)


def test_rendering_is_deterministic_and_shows_edits():
    tree = _tree()
    new = apply_edits(tree, [_edit("experience.0.b0", "Built a nightly ETL pipeline for 12 sources")])
    assert render_markdown(tree) == render_markdown(tree)
    assert "Built a nightly ETL pipeline for 12 sources" in render_markdown(new)
    assert "- Built a pipeline\n" not in render_markdown(new)
