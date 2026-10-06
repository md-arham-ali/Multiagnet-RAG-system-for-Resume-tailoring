"""
CV handling (utils/cv_handling): a CV PDF -> a CV tree -> links from its lines to
profile records, plus the tree edits the Document agent applies. Uses vectordb/
(store, embeddings, reranker, retriever) the way the agents do; the tree schema
(CVNode, CVTree, LineLink) lives in state/state.py.

  cv_ingest  : CV PDFs -> chunk vectors in the sandbox index, SECTION_TO_KB_TYPE
  cv_extract : stage 1, PDF -> CVTree (pure code, no model)
  cv_match   : stage 2, CVTree -> LineLinks (hybrid search, section by section)
  cv_edit    : apply edits to a CV tree, diff two trees, render Markdown

Explained in context/code_explanations.md, sections `scripts/match_cv_test.py`
and `agents/document.py`.
"""
