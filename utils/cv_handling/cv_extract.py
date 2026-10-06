"""
Stage 1 of CV matching: a CV PDF -> a CVTree (schema in state/state.py).
Pure code, deterministic, no model. Explained in context/code_explanations.md,
section `scripts/match_cv_test.py`.

    from utils.cv_handling.cv_extract import parse_cv
    tree, lines = parse_cv(Path("knowledge_base/input/CV_test.pdf"))
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from state.state import CVNode, CVTree, NodeKind, SectionType


# =============================================================================
# Stage 1 tables: PDF text -> CV tree
# =============================================================================

SECTION_TITLES: list[tuple[SectionType, str]] = [
    (SectionType.EDUCATION, r"(academic)?(education|qualifications?)(background)?"),
    (SectionType.EXPERIENCE,
     r"(work|professional|relevant|industry|research)?(experiences?|employment(history)?|internships?)"),
    (SectionType.PROJECTS, r"(personal|academic|selected|key|technical|relevant)?projects?"),
    (SectionType.COURSEWORK, r"(relevant)?courses?(works?)?"),
    (SectionType.SKILLS,
     r"(technical|key|core)?skills?(andtools|andinterests|summary)?|technologies|toolsandtechnologies"),
    (SectionType.ACHIEVEMENTS,
     r"(scholastic)?(awards?|honou?rs?|achievements?)(and(awards?|honou?rs?|achievements?))?"),
    (SectionType.RESPONSIBILITIES,
     r"positions?of(responsibility|responsibilities)|leadership(experience|androles)?"
     r"|extracurriculars?(activities)?|volunteering|volunteerexperience"),
    (SectionType.OTHER,
     r"publications?|certifications?|certificates?|languages|interests|hobbies"
     r"|summary|objective|references|patents?|talks"),
]
FLAT_SECTIONS = {SectionType.COURSEWORK, SectionType.ACHIEVEMENTS}
OTHER_CAN_FOLLOW = {SectionType.EXPERIENCE, SectionType.PROJECTS,
                    SectionType.RESPONSIBILITIES, SectionType.OTHER}
HEADING_SMALL_WORDS = {"of", "and", "&", "the", "for", "in"}

FIELD_NAMES: dict[SectionType, list[str]] = {
    SectionType.EXPERIENCE: ["role", "tech", "kind", "org"],
    SectionType.PROJECTS: ["title", "tech", "kind", "org"],
    SectionType.RESPONSIBILITIES: ["role", "activity", "org"],
    SectionType.EDUCATION: ["institution", "degree"],
}
TAIL_ANCHORED = {SectionType.EXPERIENCE}
ID_PREFIX = {NodeKind.ENTRY: "", NodeKind.BULLET: "b", NodeKind.ITEM: "i"}

_MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?"
_DATE = rf"(?:{_MONTH}\s*\d{{4}}|\d{{1,2}}/\d{{4}})"
_OPEN_END = r"(?:Present|present|Current|current|Now|Ongoing|Till Date)"
DATE_END = re.compile(
    rf"((?:{_DATE}|\d{{4}})\s*(?:[–—-]|to)\s*(?:{_DATE}|\d{{4}}|{_OPEN_END})|{_DATE})\s*$")
GPA_END = re.compile(
    r"((?:C?GPA|CPI|SGPA)\s*:?\s*)?\d{1,2}(?:\.\d{1,2})?\s*/\s*\d{1,3}(?:\.\d{1,2})?\s*$")
STATUS_END = re.compile(r"(In Progress|Completed|Ongoing|Maintained|Archived|Deployed|Live)\s*$")
BULLET_RE = re.compile(r"^\s*(?:[•●▪◦‣∙*]|[-–](?=\s))")
LABEL_RE = re.compile(r"^\s*([^|:]{1,40}?)\s*:\s*(.*)$")

KEEP_CAMEL = {"spaCy", "iOS", "macOS", "iPhone", "iPad", "eBay", "gRPC", "pH", "mTLS",
              "kNN", "LinkedIn", "YouTube", "PowerPoint", "PowerBI"}
WORD_TAIL = re.compile(r"(?:ed|ing|ly|tion|ment|ness|ity|ive|al|ize|ise)$")


# =============================================================================
# Stage 1: small text helpers
# =============================================================================

def squash(s: str) -> str:
    # Removes all whitespace (used to pair a default-mode line with its layout twin).
    # in : s = any text
    # out: the same text with no spaces, tabs or newlines
    return re.sub(r"\s+", "", s)


def is_bullet(s: str) -> bool:
    # Tells whether a line starts with a bullet marker (•, -, *, ...).
    # in : s = one line of text
    # out: True or False
    return bool(BULLET_RE.match(s))


def strip_marker(s: str) -> str:
    # Removes the leading bullet marker from a line.
    # in : s = one line of text
    # out: the text without its bullet marker
    return BULLET_RE.sub("", s, count=1).strip()


def heading_key(s: str) -> str:
    # Turns a heading into a comparable key ("A wards & Achievements" -> "awardsandachievements").
    # in : s = heading text
    # out: lowercase letters only, "&" read as "and"
    return re.sub(r"[^a-z]", "", s.lower().replace("&", "and"))


def looks_like_heading(s: str) -> bool:
    # Tells whether an unknown line looks like a section title (short, Title Case, no digits).
    # in : s = one line of text
    # out: True or False
    if is_bullet(s) or re.search(r"[|:\d,.;()]", s):
        return False
    words = s.split()
    return 1 <= len(words) <= 4 and all(w[0].isupper() or w.lower() in HEADING_SMALL_WORDS for w in words)


def fix_stray(s: str) -> str:
    # Joins a letter pypdf split off a word ("T rading" -> "Trading").
    # in : s = text from a line with no layout twin
    # out: the text with those stray spaces removed
    return re.sub(r"\b([B-HJ-Z]) (?=[a-z]{2,})", r"\1", s)


def classify_right(r: str) -> str:
    # Names a right-hand field: a date range, a GPA, or a status.
    # in : r = the right-hand text of a header line
    # out: "date_range", "gpa" or "status"
    if DATE_END.search(r):
        return "date_range"
    if GPA_END.search(r):
        return "gpa"
    return "status"


def peel_right(text: str, stype: SectionType) -> tuple[str, Optional[str]]:
    # Cuts a trailing date / GPA / project status off a field, even when glued on.
    # in : text = one header field, stype = the section it is in
    # out: (text without the tail, the tail or None)
    patterns = [DATE_END, GPA_END] + ([STATUS_END] if stype == SectionType.PROJECTS else [])
    for pattern in patterns:
        m = pattern.search(text)
        if m and (pattern is not STATUS_END or m.start() > 0):
            return text[:m.start()].strip(), m.group(0).strip()
    return text, None


def field_names(stype: SectionType, n: int) -> list[str]:
    # Gives the attribute names for n "|"-separated header fields in a section.
    # in : stype = section type, n = number of fields
    # out: list of n names (e.g. role, tech, kind, org)
    names = FIELD_NAMES.get(stype, ["title"])
    if n > len(names):
        return names + [f"field{i}" for i in range(len(names), n)]
    if stype in TAIL_ANCHORED and n >= 2:
        return names[: n - 1] + [names[-1]]
    return names[:n]


def split_camel(tok: str) -> str:
    # Puts back a space pypdf dropped inside one token ("improvingSharpe" -> "improving Sharpe").
    # in : tok = one space-free token
    # out: the token, split where a lost space is likely
    if tok.strip(".,;:()") in KEEP_CAMEL or re.search(r"\.[a-z]{2,}|@|/|://", tok):
        return tok
    lower_led = tok[:1].islower()
    out = [tok[:1]]
    for i in range(1, len(tok)):
        if tok[i - 1].islower() and tok[i].isupper():
            j = i - 1
            while j > 0 and tok[j - 1].islower():
                j -= 1
            word = tok[j - 1:i] if j > 0 and tok[j - 1].isupper() else tok[j:i]
            if lower_led or (len(word) >= 5 and WORD_TAIL.search(word)):
                out.append(" ")
        out.append(tok[i])
    return "".join(out)


def repair_text(s: str) -> str:
    # Repairs the spacing pypdf lost in a sentence (bullets and flat items only).
    # in : s = raw sentence text
    # out: the sentence with likely missing spaces put back
    s = " ".join(s.split())
    s = re.sub(r"(\d)(st|nd|rd|th)(?=[a-z])", r"\1\2 ", s)
    s = re.sub(r"(?<=%)(?=[A-Za-z])", " ", s)
    s = re.sub(r"(?<=\w)\((?=[A-Z0-9])", " (", s)
    toks = []
    for tok in s.split(" "):
        if not re.search(r"\.[a-z]{2,}|@|://", tok):
            tok = split_camel(tok)
            tok = re.sub(r"(?<=[a-z]{2})(?=\d)", " ", tok)
            tok = re.sub(r"^([a-z])(?=\d+(?:\.\d+)?%)", r"\1 ", tok)
            tok = re.sub(r"(?<=\d)(?!(?:st|nd|rd|th)\b)(?=[a-z]{2,})", " ", tok)
        toks.append(tok)
    return " ".join(toks)


def split_elements(body: str) -> list[str]:
    # Splits a skills list on "|" (or "," / ";"), never inside parentheses.
    # in : body = the text after a skills label, e.g. "Python (Pandas, NumPy)|SQL"
    # out: list of skill strings, e.g. ["Python (Pandas, NumPy)", "SQL"]
    seps = "|" if "|" in body else ",;"
    out, cur, depth = [], [], 0
    for ch in body:
        depth += (ch in "([") - (ch in ")]" and depth > 0)
        if ch in seps and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return [" ".join(x.split()) for x in out if x.strip()]


# =============================================================================
# Stage 1: PDF lines
# =============================================================================

@dataclass
class Line:
    # One non-empty PDF line: default-mode text, its page, and its layout-mode twin.
    raw: str
    page: int
    layout: Optional[str] = None

    @property
    def clean(self) -> str:
        # Readable text of the line (layout twin when there is one).
        # out: the text with whitespace collapsed
        return " ".join((self.layout or self.raw).split())

    @property
    def bullet(self) -> bool:
        # out: True if the line starts with a bullet marker
        return is_bullet(self.clean)

    @property
    def has_date(self) -> bool:
        # out: True if the line ends with a date or date range
        return bool(DATE_END.search(self.clean))

    @property
    def starts_entry(self) -> bool:
        # Tells whether the line opens a new entry rather than continuing a wrapped bullet.
        # out: True if it has "|", a trailing date, or a right-aligned field
        return "|" in self.clean or self.has_date or self.split_right()[1] is not None

    def split_right(self) -> tuple[str, Optional[str]]:
        # Splits off the right-aligned field (date / status / GPA) using the layout gap.
        # out: (left text, right text or None)
        if self.layout is None:
            return self.clean, None
        parts = re.split(r"\s{3,}", self.layout.strip())
        if len(parts) >= 2:
            return " ".join(" ".join(parts[:-1]).split()), parts[-1].strip()
        return self.clean, None


def read_lines(pdf: Path) -> list[Line]:
    # Reads every non-empty line of a PDF and pairs it with its layout-mode twin.
    # in : pdf = path to a PDF file
    # out: list of Line in reading order
    from pypdf import PdfReader

    lines: list[Line] = []
    for page_no, page in enumerate(PdfReader(str(pdf)).pages):
        try:
            layout = page.extract_text(extraction_mode="layout") or ""
        except Exception as e:
            print(f"  ! layout extraction failed on page {page_no}: {e}")
            layout = ""
        twins: dict[str, str] = {}
        for ln in layout.splitlines():
            if ln.strip():
                twins.setdefault(squash(ln), ln)
        for ln in (page.extract_text() or "").splitlines():
            if ln.strip():
                lines.append(Line(raw=ln, page=page_no, layout=twins.get(squash(ln))))
    return lines


def known_section(line: Line) -> Optional[SectionType]:
    # Recognises a known section heading (Education, Experience, Skills, ...).
    # in : line = one PDF line
    # out: its SectionType, or None if it is not a known heading
    s = line.clean
    if is_bullet(s) or "|" in s or ":" in s.rstrip(":") or len(s.split()) > 6:
        return None
    key = heading_key(s)
    return next((stype for stype, pat in SECTION_TITLES if key and re.fullmatch(pat, key)), None)


def header_parts(line: Line, stype: SectionType, split_pipes: bool = True) -> tuple[list[str], Optional[str]]:
    # Breaks a header line into its fields and its right-hand tail (date / GPA / status).
    # in : line = header line, stype = section, split_pipes = split on "|" or keep one field
    # out: (list of field texts, right-hand text or None)
    left, right = line.split_right()
    if line.layout is None:
        left = fix_stray(left)
    fields = [f.strip() for f in left.split("|") if f.strip()] if split_pipes else ([left] if left else [])
    if right is None and fields:
        last, right = peel_right(fields[-1], stype)
        if last:
            fields[-1] = last
        else:
            fields.pop()
    return fields, right


def split_entry_header(line: Line, stype: SectionType) -> tuple[dict[str, str], str]:
    # Turns an entry header ("role|tech|kind|org  date") into named attributes.
    # in : line = entry header line, stype = its section
    # out: (attrs dict like {"role": ..., "org": ..., "date_range": ...}, entry title)
    fields, right = header_parts(line, stype)
    attrs = dict(zip(field_names(stype, len(fields)), fields))
    if right:
        attrs[classify_right(right)] = right
    return attrs, (fields[0] if fields else line.clean)


def has_bullets(node: Optional[CVNode]) -> bool:
    # out: True if the node already has bullet children
    return node is not None and any(c.kind == NodeKind.BULLET for c in node.children)


def walk(node: CVNode):
    # Visits a node and all nodes below it, top to bottom.
    # in : node = any tree node
    # out: generator of nodes (the node first)
    yield node
    for c in node.children:
        yield from walk(c)


# =============================================================================
# Stage 1: tree builder
# =============================================================================

class TreeBuilder:
    # Reads the lines once, top to bottom, and grows the CV tree.

    def __init__(self, source_file: str) -> None:
        # in : source_file = PDF file name (stored on the tree)
        self.source_file = source_file
        self.root = CVNode(node_id="cv", kind=NodeKind.CV, section_type=SectionType.OTHER,
                           depth=0, title=source_file)
        self.section: Optional[CVNode] = None
        self.entry: Optional[CVNode] = None
        self.last: Optional[CVNode] = None
        self._section_ids: Counter = Counter()
        self._base: dict[str, str] = {}
        self._bulleted: set[str] = set()
        self._groups: dict[str, tuple[CVNode, str]] = {}

    def open_section(self, stype: SectionType, line: Optional[Line] = None) -> None:
        # Starts a new section node (a heading line, or the implicit header block).
        # in : stype = section type, line = the heading line (None for the header block)
        n = self._section_ids[stype.value]
        self._section_ids[stype.value] += 1
        title = line.clean if line else "Header"
        node = CVNode(node_id=stype.value if n == 0 else f"{stype.value}_{n}", kind=NodeKind.SECTION,
                      section_type=stype, depth=1, parent_id="cv", title=title, text=title,
                      raw_text=line.raw if line else "", page=line.page if line else None)
        self.root.children.append(node)
        self.section, self.entry, self.last = node, None, node

    def may_open_other(self, line: Line, nxt: Optional[Line]) -> bool:
        # Decides whether an unknown title-like line starts an `other` section.
        # in : line = current line, nxt = the next line (or None)
        # out: True to open an `other` section
        sec = self.section
        return (sec is not None and sec.section_type in OTHER_CAN_FOLLOW
                and has_bullets(self.entry)
                and not (nxt is not None and nxt.bullet)
                and looks_like_heading(line.clean))

    def add_line(self, line: Line) -> None:
        # Places one non-heading line into the tree, by section kind.
        # in : line = one PDF line
        if self.section is None:
            self.open_section(SectionType.HEADER)
        stype = self.section.section_type
        if stype == SectionType.HEADER:
            self._add(self.section, NodeKind.ITEM, line, line.clean)
        elif stype == SectionType.SKILLS:
            self._skills(line)
        elif stype in FLAT_SECTIONS:
            self._flat(line)
        else:
            self._entry_section(line)

    def _add(self, parent: CVNode, kind: NodeKind, line: Optional[Line], text: str,
             repair: bool = False, bulleted: bool = False, **fields) -> CVNode:
        # Creates any child node (entry, bullet, item) with a position-based id.
        # in : parent = node to attach to, kind = node kind, line = source line (None for a
        #      skill fragment), text = node text, repair = run repair_text, bulleted = came
        #      from a "•" line, fields = extra CVNode fields (title, attrs)
        # out: the new node (also becomes self.last)
        n = sum(c.kind == kind for c in parent.children)
        node = CVNode(node_id=f"{parent.node_id}.{ID_PREFIX[kind]}{n}", kind=kind,
                      section_type=parent.section_type, depth=parent.depth + 1,
                      parent_id=parent.node_id, text=repair_text(text) if repair else text,
                      raw_text=line.raw if line else text, page=line.page if line else parent.page,
                      **fields)
        parent.children.append(node)
        self._base[node.node_id] = text
        if bulleted:
            self._bulleted.add(node.node_id)
        self.last = node
        return node

    def _append(self, node: CVNode, line: Line) -> None:
        # Adds one more raw PDF line to an existing node.
        # in : node = node to extend, line = the extra line
        node.raw_text += "\n" + line.raw

    def _continue(self, node: CVNode, line: Line) -> None:
        # Joins a wrapped line onto the bullet / item it continues.
        # in : node = the bullet or item, line = its wrapped continuation
        base = self._base.get(node.node_id, node.text) + " " + line.clean
        self._base[node.node_id] = base
        node.text = repair_text(base)
        self._append(node, line)

    def _entry_section(self, line: Line) -> None:
        # Handles a line in an entry section (experience, projects, education, ...).
        # in : line = one PDF line
        if line.bullet:
            if self.entry is None:
                self._add(self.section, NodeKind.ITEM, line, strip_marker(line.clean), repair=True, bulleted=True)
            else:
                self._add(self.entry, NodeKind.BULLET, line, strip_marker(line.clean), repair=True)
        elif (self.section.section_type == SectionType.EDUCATION and self.entry is not None
              and "degree" not in self.entry.attrs and not has_bullets(self.entry) and not line.has_date):
            self._education_detail(self.entry, line)
        elif self.last is not None and self.last.kind == NodeKind.BULLET and not line.starts_entry:
            self._continue(self.last, line)
        else:
            attrs, title = split_entry_header(line, self.section.section_type)
            self.entry = self._add(self.section, NodeKind.ENTRY, line,
                                   " | ".join(attrs.values()) or line.clean, title=title, attrs=attrs)

    def _education_detail(self, entry: CVNode, line: Line) -> None:
        # Stores the degree / GPA line on the school entry above it.
        # in : entry = the school entry, line = the degree line
        fields, right = header_parts(line, SectionType.EDUCATION, split_pipes=False)
        if fields:
            entry.attrs["degree"] = fields[0]
        if right:
            entry.attrs[classify_right(right)] = right
        self._append(entry, line)
        entry.text = " | ".join(entry.attrs.values())
        self.last = entry

    def _flat(self, line: Line) -> None:
        # Handles a line in a flat section (coursework, achievements): one item per line.
        # in : line = one PDF line
        if line.bullet:
            self._add(self.section, NodeKind.ITEM, line, strip_marker(line.clean), repair=True, bulleted=True)
        elif self.last is not None and self.last.node_id in self._bulleted:
            self._continue(self.last, line)
        else:
            self._add(self.section, NodeKind.ITEM, line, line.clean, repair=True)

    def _skills(self, line: Line) -> None:
        # Handles a skills line: a new "Label: a|b|c" group, or a wrapped part of the last group.
        # in : line = one PDF line
        text = strip_marker(line.clean) if line.bullet else line.clean
        if line.layout is None:
            text = fix_stray(text)
        m = LABEL_RE.match(text)
        last = self.last
        in_group = last is not None and last.kind == NodeKind.ENTRY and last.parent_id == self.section.node_id
        group = last if in_group else None
        if m or group is None or line.bullet:
            label, body = (m.group(1).strip(), m.group(2)) if m else ("", text)
            node = self._add(self.section, NodeKind.ENTRY, line, "", title=label,
                             attrs={"group": label} if label else {})
            self._groups[node.node_id] = (node, body.strip())
        else:
            node, prev = self._groups[group.node_id]
            glue = "" if prev.endswith("|") or text.startswith("|") else " "
            self._groups[group.node_id] = (node, prev + glue + text)
            self._append(group, line)

    def finish(self) -> CVTree:
        # Splits every skills group into one item per skill and returns the tree.
        # out: the finished CVTree
        for group, body in self._groups.values():
            group.text = f"{group.title}: {body}" if group.title else body
            for element in split_elements(body):
                attrs = {"fragment": "1", **({"group": group.title} if group.title else {})}
                self._add(group, NodeKind.ITEM, None, element, attrs=attrs)
        return CVTree(source_file=self.source_file, root=self.root)


def parse_cv(pdf: Path) -> tuple[CVTree, list[Line]]:
    # Stage 1 entry point: turns a CV PDF into a CV tree.
    # in : pdf = path to the CV PDF
    # out: (the CVTree, the PDF lines it was built from)
    lines = read_lines(pdf)
    builder = TreeBuilder(pdf.name)
    for i, line in enumerate(lines):
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        stype = known_section(line)
        if stype is None and builder.may_open_other(line, nxt):
            stype = SectionType.OTHER
        if stype is None:
            builder.add_line(line)
        else:
            builder.open_section(stype, line)
    return builder.finish(), lines


def line_problems(tree: CVTree, lines: list[Line]) -> list[str]:
    # Checks that every PDF line landed in exactly one tree node.
    # in : tree = parsed tree, lines = the PDF lines
    # out: list of problems ("lost: ..." / "duplicate: ..."), empty when all is well
    seen: Counter = Counter()
    for n in walk(tree.root):
        if n.raw_text and n.attrs.get("fragment") != "1":
            seen.update(n.raw_text.split("\n"))
    want = Counter(l.raw for l in lines)
    return ([f"lost:      {l!r}" for l in (want - seen).elements()]
            + [f"duplicate: {l!r}" for l in (seen - want).elements()])


def short(s: str, n: int = 70) -> str:
    # Shortens text for a one-line printout.
    # in : s = text, n = max length
    # out: text of at most n characters
    s = s.replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


def print_parse(tree: CVTree, lines: list[Line]) -> None:
    # Prints each section's shape and the every-line-once check.
    # in : tree = parsed tree, lines = the PDF lines
    print(f"\n=== parse: {tree.source_file}  ({len(lines)} lines, {len(tree.root.children)} sections)")
    for sec in tree.root.children:
        entries = [c for c in sec.children if c.kind == NodeKind.ENTRY]
        items = sum(c.kind == NodeKind.ITEM for c in sec.children)
        if sec.section_type == SectionType.SKILLS:
            parts = [f"{len(entries)} groups (items: {', '.join(str(len(g.children)) for g in entries)})"]
        elif entries:
            sizes = ", ".join(str(sum(b.kind == NodeKind.BULLET for b in e.children)) for e in entries)
            parts = [f"{len(entries)} entries (bullets: {sizes})"]
        else:
            parts = []
        if items:
            parts.append(f"{items} items")
        print(f"  {sec.node_id:<18} {short(sec.title, 32):<32} {', '.join(parts)}")
    problems = line_problems(tree, lines)
    print("  every PDF line lands in exactly one node: OK" if not problems
          else f"  ! every-line-once invariant BROKEN ({len(problems)}):\n" + "\n".join(f"      {p}" for p in problems))
