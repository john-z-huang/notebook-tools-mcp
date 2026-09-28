"""Notebook Tools MCP Server — lightweight read/search/edit for Jupyter notebooks."""

__version__ = "0.4.0"

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "notebook-tools",
    instructions="""\
Efficient .ipynb navigation — use INSTEAD of the built-in Read tool for notebooks.

Reading notebooks with the Read tool loads raw JSON (base64 images, metadata) wasting
100K+ tokens. These tools parse cell structure and return only source code and text.

WHEN TO USE WHICH TOOL:

  Reading .ipynb files:
    nb_overview    → ALWAYS start here. Shows cell index, type, line count, first-line preview.
    nb_read_cell   → Read one cell by index. Use include_outputs=true only when you need output.
    nb_read_cells  → Read a range: "0,1,5-8". Faster than multiple nb_read_cell calls.
    nb_read_section → Read cells under a markdown heading until next same-level heading.
    nb_headings    → List all markdown headings with cell indices. Use before nb_read_section.
    nb_metadata    → Kernel info, cell counts, file/output sizes. Use for triage.

  Searching .ipynb files:
    nb_search      → Regex search within ONE notebook. Use INSTEAD OF Grep for .ipynb files.
    nb_search_dir  → Regex search across ALL notebooks in a directory.

  Writing .ipynb files:
    nb_write_cell  → Overwrite cell source by index. Use when you already know the index from nb_overview/nb_read_cell.
    nb_insert_cell → Insert new cell at position. Use cell_index=-1 to append.
    nb_delete_cell → Delete cell by index.
    nb_batch_write_cells → Batch overwrite and/or insert many cells in ONE call (one load/save). Prefer this over repeated nb_write_cell/nb_insert_cell calls.

  VS BUILT-IN TOOLS:
    Use nb_* tools instead of Read for .ipynb — 400-3000x fewer tokens.
    Use nb_search instead of Grep for .ipynb — Grep sees raw JSON, nb_search sees cell source.
    Use nb_write_cell when you already have the cell index from nb_overview.
    Use NotebookEdit when you have a cell_id from another source (e.g. VS Code).
    Never use both nb_write_cell AND NotebookEdit on the same cell in sequence.

  WORKFLOW: nb_overview → identify cell index → nb_read_cell or nb_search → nb_write_cell.
  All tools use integer cell indices. nb_overview shows the indices you need for everything else.
""",
)
