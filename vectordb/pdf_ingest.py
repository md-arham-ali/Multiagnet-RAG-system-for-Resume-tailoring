"""
PDF ingestion for the SANDBOX vector index (test_work/ -> test_vb/).

Mirrors vectordb/ingest.py, but the input is PDFs instead of JSON fixtures, so
there is one extra step JSON never needed: chunking. A PDF is one long document;
embedding it whole averages its whole meaning into a single vector and destroys
retrieval precision. So we split each PDF's text into smaller pieces, and each
CHUNK becomes its own (id, text, metadata) row — exactly the shape store.add
already expects.

Pipeline per file:   PDF --extract_text--> str --chunk_text--> [chunks]
                     --> (ids, texts, metadatas) --> store.add(collection, ...)

This is scratch/experiment code: it writes to a SEPARATE Chroma index
(VectorStore(persist_dir="test_work/test_vb")) and never touches the real KB
index under knowledge_base/chroma/.
"""

from __future__ import annotations

from pathlib import Path

from vectordb.store import VectorStore


# --- DONE (plumbing): pull raw text out of a PDF -----------------------------
def extract_text(path: Path) -> str:
    """Concatenate the text layer of every page in a PDF into one string.

    Uses pypdf, which reads the PDF's existing text layer — it does NOT do OCR.
    A scanned/image-only PDF has no text layer, so this returns mostly empty
    strings for such files (that's the 'is it a text PDF?' caveat, made real).
    """
    from pypdf import PdfReader  # lazy import: keeps module import cheap

    reader = PdfReader(str(path))
    pages = [(page.extract_text() or "") for page in reader.pages]
    return "\n\n".join(pages)


# --- YOUR CODE (brain #1): how to split the text -----------------------------
def chunk_text(text: str) -> list[str]:
    """Split one PDF's text into embeddable chunks.

    YOUR DESIGN DECISION — this directly controls retrieval quality:
      - too large  -> back to the 'averaged vector' problem (imprecise hits),
      - too small  -> a single idea gets fragmented across chunks (lost context).

    Suggested tool (already installed, not yet used anywhere in the repo):
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=...,      # you pick (chars) — e.g. start ~800
            chunk_overlap=...,   # you pick (chars) — e.g. start ~100
        )
        return splitter.split_text(text)

    RecursiveCharacterTextSplitter tries to break on natural boundaries first
    (paragraph -> line -> sentence -> word) so chunks stay coherent. The overlap
    repeats a little text between neighbours so an idea straddling a boundary
    isn't cut in half.
    """
    from langchain_text_splitters import RecursiveCharacterTextSplitter 

    splitter = RecursiveCharacterTextSplitter(
    chunk_size = 400,
    chunk_overlap = 70,
    )

    return splitter.split_text(text)




# --- DONE (plumbing): walk a folder of PDFs and index every chunk ------------
def build_from_folder(
    store: VectorStore,
    folder: Path,
    collection: str = "pdf_documents",
    reset: bool = True,
) -> dict[str, int]:
    """Extract -> chunk -> embed -> index every *.pdf in `folder`.

    Returns {pdf_filename: chunk_count}. Idempotent by id: re-running upserts
    the same ids rather than duplicating (but see plan caveat — a re-chunk that
    produces FEWER chunks leaves stale trailing ids unless you reset first).
    """
    if reset:
        store.reset(collection)

    counts: dict[str, int] = {}
    for pdf in sorted(folder.glob("*.pdf")):
        text = extract_text(pdf)
        chunks = chunk_text(text)
        if not chunks:
            counts[pdf.name] = 0
            continue

        ids, texts, metas = [], [], []
        for i, chunk in enumerate(chunks):
            ids.append(f"{pdf.stem}:{i}")
            texts.append(chunk)
            # --- YOUR CODE (brain #2): what to tag each chunk with -----------
            # Whatever you put here is what a Hit can be traced back to later.
            # Chroma metadata must be scalars (str/int/float/bool), no lists/dicts.
            # Decide the fields — e.g. source_file, chunk_index, (page?).
            meta = {
                "type": "pdf_chunk",
                "source_file" : pdf.name,   # was hardcoded "CV_11c.pdf" — every chunk claimed the wrong source
                "chunk_index" : i,
            }
            metas.append(meta)

        store.add(collection, ids, texts, metas)
        counts[pdf.name] = len(ids)

    return counts
