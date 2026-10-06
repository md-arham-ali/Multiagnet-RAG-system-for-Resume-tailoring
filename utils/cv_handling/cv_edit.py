"""
Tree mechanics for the Document agent: carry out edits on a CV tree, list what
changed, render the tree as Markdown. Pure code, no model.

What this module does NOT do is decide which edits are allowed - that is the
agent's guard step. It is strict on purpose: handed an edit it cannot carry out
(unknown id, a section or entry header, empty text, two edits on one line, an
action other than 'replace') it raises, so a hole in the guards shows up as an
error instead of a silently wrong CV.

    from utils.cv_handling.cv_edit import apply_edits, changed_lines, render_markdown
    new_tree = apply_edits(state.cv_tree, patches.edits)   # state.cv_tree is untouched
    changes = changed_lines(state.cv_tree, new_tree)
    markdown = render_markdown(new_tree)
"""

from __future__ import annotations

from pydantic import BaseModel

from state.state import CVNode, CVTree, Edit, EditAction, NodeKind, SectionType
from utils.cv_handling.cv_extract import walk

# Only a sentence-like leaf takes new text. Sections and entry headers carry
# structure (names, employers, dates), so an edit that targets one is a bug upstream.
EDITABLE_KINDS = {NodeKind.BULLET, NodeKind.ITEM}


class LineChange(BaseModel):
    node_id: str
    before: str   # "" when the line is not in the old tree
    after: str    # "" when the line is not in the new tree


def index_nodes(tree: CVTree) -> dict[str, CVNode]:
    # in : tree = a CV tree
    # out: {node_id: node} for every node, the root included
    return {n.node_id: n for n in walk(tree.root)}


def apply_edits(tree: CVTree, edits: list[Edit]) -> CVTree:
    # Applies replace edits to a copy of the tree. The input tree is never touched,
    # so any draft can be rebuilt from the original CV plus a patch set.
    # in : tree = the original CV, edits = already-validated edits (action 'replace' only)
    # out: a new tree; only the targeted nodes' `text` differs (`raw_text` keeps the PDF's own text)
    # raises: NotImplementedError (action not 'replace'), KeyError (unknown target),
    #         ValueError (target is not a bullet/item, empty new_text, target edited twice)
    out = tree.model_copy(deep=True)
    nodes = index_nodes(out)
    done: set[str] = set()
    for edit in edits:
        if edit.action != EditAction.REPLACE:
            raise NotImplementedError(
                f"edit on {edit.target_id!r}: action {edit.action.value!r} is not supported, only 'replace'"
            )
        node = nodes.get(edit.target_id)
        if node is None:
            raise KeyError(f"edit targets unknown node {edit.target_id!r}")
        if node.kind not in EDITABLE_KINDS:
            raise ValueError(
                f"edit targets {edit.target_id!r}, a {node.kind.value}: only a bullet or an item can take new text"
            )
        if edit.target_id in done:
            raise ValueError(f"two edits target {edit.target_id!r}")
        text = " ".join((edit.new_text or "").split())
        if not text:
            raise ValueError(f"edit on {edit.target_id!r} has no new_text")
        node.text = text
        done.add(edit.target_id)
    return out


def changed_lines(old: CVTree, new: CVTree) -> list[LineChange]:
    # Which lines differ between two trees (the gate-4 diff, and what Critic/Verifier check first).
    # in : old, new = two CV trees
    # out: one LineChange per node whose text differs, in the new tree's order
    #      (a node present in only one tree counts as a change from/to "")
    before = {n.node_id: n.text for n in walk(old.root)}
    after = {n.node_id: n.text for n in walk(new.root)}
    ids = list(after) + [nid for nid in before if nid not in after]
    return [
        LineChange(node_id=nid, before=before.get(nid, ""), after=after.get(nid, ""))
        for nid in ids
        if before.get(nid, "") != after.get(nid, "")
    ]


def render_markdown(tree: CVTree) -> str:
    # Renders the CV as Markdown, sections in the CV's own order.
    # in : tree = a CV tree (original or patched)
    # out: Markdown text. Not the PDF's layout: the tree keeps text, not styling.
    blocks = [b for b in (_section_block(s) for s in tree.root.children) if b]
    return "\n\n".join(blocks) + "\n"


def _section_block(section: CVNode) -> str:
    if section.section_type == SectionType.HEADER:
        lines = [c.text for c in section.children if c.text]
        if not lines:
            return ""
        head = f"# {lines[0]}"
        return head + ("\n\n" + "  \n".join(lines[1:]) if len(lines) > 1 else "")

    parts = [f"## {section.title}"]
    loose: list[str] = []            # list lines that sit directly under the section

    def flush() -> None:
        if loose:
            parts.append("\n".join(loose))
            loose.clear()

    for child in section.children:
        if child.kind == NodeKind.ENTRY and section.section_type == SectionType.SKILLS:
            loose.append(_skill_group(child))
        elif child.kind == NodeKind.ENTRY:
            flush()
            rows = [f"### {child.text}"] + [f"- {c.text}" for c in child.children if c.text]
            parts.append("\n".join(rows))
        elif child.text:
            loose.append(f"- {child.text}")
    flush()
    return "\n\n".join(parts)


def _skill_group(group: CVNode) -> str:
    # A skills group is rebuilt from its items, not from group.text, which is
    # the PDF's joined line and would go stale after an item is edited.
    items = [c.text for c in group.children if c.text]
    if not items:
        return f"- {group.text}"
    label = group.attrs.get("group") or group.title
    body = " | ".join(items)
    return f"- **{label}:** {body}" if label else f"- {body}"
