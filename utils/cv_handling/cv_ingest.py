"""
Sandbox CV ingest: CV PDFs -> chunk vectors in the sandbox index, plus the map
from a CV section to the KB `type` its profile records carry. Explained in
context/code_explanations.md, section `scripts/match_cv_test.py`.

    from utils.cv_handling.cv_ingest import ingest_cvs, ingested_pdfs, SECTION_TO_KB_TYPE
    ingest_cvs()          # knowledge_base/input/*.pdf -> test_work/test_vb
    ingested_pdfs()       # ["CV_test.pdf", ...]

The CV tree schema (CVNode, CVTree, LineLink, ...) lives in state/state.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import config
from state.state import SectionType
from vectordb.pdf_ingest import build_from_folder

PDF_COLLECTION = "pdf_documents"

# Section -> the KB `type` its records carry in the profile collection (the
# metadata "type" written by vectordb/ingest.py). Sections with no KB type map to
# None and are not matched.
SECTION_TO_KB_TYPE: dict[SectionType, Optional[str]] = {
    SectionType.HEADER: None,
    SectionType.EDUCATION: "education",
    SectionType.EXPERIENCE: "work_experience",
    SectionType.PROJECTS: "project",
    SectionType.COURSEWORK: "coursework",
    SectionType.SKILLS: "skill",
    SectionType.ACHIEVEMENTS: "achievement",
    SectionType.RESPONSIBILITIES: "extracurricular",
    SectionType.OTHER: None,
}


def _collection(index_dir: Path, collection: str):
    # Opens one collection of a Chroma index without loading any embedding model.
    # in : index_dir = Chroma folder, collection = collection name
    # out: the collection, or None if the index or the collection does not exist
    import chromadb

    if not Path(index_dir).exists():
        return None
    client = chromadb.PersistentClient(path=str(index_dir))
    if collection not in [c.name for c in client.list_collections()]:
        return None
    return client.get_collection(collection)


def ingest_cvs(input_dir: Path = config.CV_INPUT_DIR, index_dir: Path = config.CV_SANDBOX_DIR,
               collection: str = PDF_COLLECTION) -> dict[str, int]:
    # Chunks and embeds every CV PDF in a folder into the sandbox index (replaces the old chunks).
    # in : input_dir = folder of CV PDFs, index_dir = sandbox Chroma folder, collection = target collection
    # out: {pdf file name: chunk count}; empty (index untouched) when the folder has no PDFs
    from vectordb.store import VectorStore

    if not any(Path(input_dir).glob("*.pdf")):
        return {}
    return build_from_folder(VectorStore(persist_dir=index_dir), Path(input_dir), collection=collection)


def ingested_pdfs(index_dir: Path = config.CV_SANDBOX_DIR, collection: str = PDF_COLLECTION) -> list[str]:
    # Lists the PDF names that are in the sandbox index.
    # in : index_dir = sandbox Chroma folder, collection = CV chunk collection
    # out: sorted PDF file names (empty if nothing is indexed)
    col = _collection(index_dir, collection)
    if col is None:
        return []
    metas = col.get(include=["metadatas"])["metadatas"]
    return sorted({m["source_file"] for m in metas if m and m.get("source_file")})


def indexed_chunks(index_dir: Path = config.CV_SANDBOX_DIR, collection: str = PDF_COLLECTION) -> int:
    # Counts the chunks in the sandbox CV collection.
    # in : index_dir = sandbox Chroma folder, collection = CV chunk collection
    # out: number of chunks (0 if the collection does not exist)
    col = _collection(index_dir, collection)
    return 0 if col is None else col.count()
