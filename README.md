# notebook-tools-mcp

MCP server for Jupyter notebook navigation and editing. Reads `.ipynb` files directly as JSON — no Jupyter server, no kernel, no overhead.

## Problem

AI CLI agents (Claude Code, Gemini CLI, Codex) working inside VS Code Dev Containers don't have a good way of interacting with Jupyter notebooks. Notebooks are JSON files where 90%+ of the bytes are base64-encoded image outputs and execution metadata. Reading a 1MB notebook with a standard file-read tool wastes ~294K tokens on noise. Agents re-invent notebook parsing logic every session, burning tokens on the same problem repeatedly.

## Architecture

6 files, ~840 lines, zero dependencies beyond `mcp>=2.1,<3`:

```
notebook_tools_mcp/
  __init__.py      (45L)  MCPServer instance + server instructions
  _helpers.py      (208L) Shared utilities: load/save, cell formatting, parsing, addressing
  read_tools.py    (250L) 6 read tools
  search_tools.py  (125L) 2 search tools
  write_tools.py   (198L) 4 write tools
  server.py        (16L)  Entry point
```

Each file < 260 lines. Single responsibility. Shared helpers avoid duplication. No circular imports.

## Design decisions

**No Jupyter server.** Works in remote VS Code Dev Containers (Docker) over SSH. Adding a Jupyter server means extra memory, extra complexity, zero value when VS Code already renders notebooks natively.

**No dependencies beyond `mcp`.** Notebooks are JSON. Python's stdlib `json` module reads them perfectly. `nbformat` (and its 50+ transitive Jupyter ecosystem deps) is unnecessary weight.

**No execution.** Running code requires a kernel, which requires a server. That's the complexity this tool exists to avoid.

**stdio transport only.** Launched on demand by the MCP client, communicates via stdin/stdout, exits when done. No HTTP endpoints, no WebSocket connections, no persistent processes.

**Consistent index-based addressing.** All 12 tools use integer cell indices. `nb_overview` shows indices → `nb_read_cell(15)` reads → `nb_write_cell(15, ...)` edits. One addressing scheme throughout. (`nb_batch_write_cells` also accepts a cell `id` string, for when the reference comes from outside the `nb_overview` flow.)

**`sort_keys=True` on save.** Matches Jupyter/nbformat convention for deterministic output. Prevents noisy git diffs from key reordering between load/save cycles.

### Write tools vs NotebookEdit

Claude Code has a built-in `NotebookEdit` tool (addresses cells by `cell_id` or `cell_number`). This server also provides write tools. Both are kept intentionally:

| | MCP write tools | NotebookEdit (built-in) |
|---|---|---|
| Addressing | Integer index (matches `nb_overview`) | `cell_id` string or `cell_number` (0-indexed) |
| Best for | Within the `nb_overview` → read → edit flow | When VS Code or another tool provides the cell_id |
| Footprint | 198 lines | Built-in |

The MCP write tools exist for **workflow cohesion** — an agent using `nb_overview` to find a cell already has its index. Requiring a lookup to get the `cell_id` for NotebookEdit would add a pointless extra step.

### Tools we deliberately did NOT build

These were considered and rejected because `nb_search` / `nb_search_dir` already cover them:

| Rejected tool | Why `nb_search` is sufficient |
|---|---|
| `nb_dependencies(var)` | `nb_search(path, "var_name")` returns definitions and usages; LLMs trivially distinguish `x = ...` from `...x...` |
| `nb_function_map` | `nb_search_dir(dir, "^def\\s+\\w+", cell_type="code")` |
| `nb_imports_all` | `nb_search_dir(dir, "^import\|^from\\s+\\w+\\s+import")` |
| `nb_compare_cells` | Agent calls `nb_read_cell` twice |

Building AST-based dependency tracking would add ~200+ lines of fragile code that breaks across Python/R/Julia/bash cells. Not worth it when regex search + LLM reasoning achieves the same result.

### How agents discover when to use these tools

Claude Code (and similar agents) decide which tool to use based on three channels, in order of priority:

1. **MCP server `instructions`** — set via `MCPServer(instructions=...)` in `__init__.py`. Injected into the system prompt of every conversation where the server is connected. This is where the "use nb_search INSTEAD OF Grep for .ipynb" guidance lives. Agents see this before any tool is called.

2. **Tool docstrings** — the `"""..."""` on each `@mcp.tool()` function. Shown when the agent discovers tools (e.g. via ToolSearch). Each docstring says what the tool does AND when to prefer it over alternatives.

3. **CLAUDE.md** — project-level instructions always loaded into context. Contains a decision table mapping tasks to tools (e.g. "Read notebook → nb_overview, NOT Read tool").

All three channels reinforce the same message: use `nb_*` tools for `.ipynb`, never `Read`/`Grep`.

## Install

```bash
# pip
pip install git+https://github.com/tony-zhelonkin/notebook-tools-mcp.git

# uv
uv pip install git+https://github.com/tony-zhelonkin/notebook-tools-mcp.git
```

For development (editable install from a local clone):

```bash
git clone https://github.com/tony-zhelonkin/notebook-tools-mcp.git
pip install -e notebook-tools-mcp/
```

## Configure

Add to `.mcp.json`:

```json
{
  "mcpServers": {
    "notebook-tools": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "notebook_tools_mcp.server"]
    }
  }
}
```

Or toggle via [SciAgent-toolkit](https://github.com/tony-zhelonkin/SciAgent-toolkit) addon system:

```bash
./scripts/manage-addon.sh enable notebook-tools --project-dir /path/to/project
./scripts/manage-addon.sh disable notebook-tools --project-dir /path/to/project
```

## Tools

All tools take `notebook_path` (absolute path) as first parameter unless noted.

### Read tools

| Tool | Parameters | What it does |
|------|-----------|-------------|
| `nb_metadata` | `notebook_path` | Kernel info, format version, cell counts, file size, output size |
| `nb_overview` | `notebook_path`, `include_output_sizes=true` | Cell index, type, line/char count, first-line preview, output sizes |
| `nb_read_cell` | `notebook_path`, `cell_index`, `include_outputs=false`, `max_output_chars=2000` | Full source of one cell by index, optional truncated outputs |
| `nb_read_cells` | `notebook_path`, `cell_indices` (e.g. `"0,1,5-8"`), `cell_type=null`, `include_outputs=false` | Batch read with range syntax, optional type filter |
| `nb_read_section` | `notebook_path`, `header`, `max_cells=50`, `include_outputs=false` | All cells from a markdown heading to the next same-or-higher-level heading |
| `nb_headings` | `notebook_path` | All markdown headings with cell indices and levels |

### Search tools

| Tool | Parameters | What it does |
|------|-----------|-------------|
| `nb_search` | `notebook_path`, `pattern` (regex), `cell_type=null`, `context_lines=1` | Regex search across cells with context, optional type filter |
| `nb_search_dir` | `directory`, `pattern` (regex), `cell_type=null`, `context_lines=0` | Search all `.ipynb` files in a directory, grouped by notebook |

### Write tools

| Tool | Parameters | What it does |
|------|-----------|-------------|
| `nb_write_cell` | `notebook_path`, `cell_index`, `source` | Overwrite source content of an existing cell |
| `nb_insert_cell` | `notebook_path`, `cell_index` (`-1` to append), `cell_type`, `source` | Insert a new cell at position |
| `nb_delete_cell` | `notebook_path`, `cell_index` | Delete a cell |
| `nb_batch_write_cells` | `notebook_path`, `writes=[{"cell_id", "source"}]`, `inserts=[{"after_cell_id", "cells": [{"cell_type", "source"}]}]` | Overwrite and/or insert many cells in one load/save. `cell_id` / `after_cell_id` accept an integer index or a cell id string. All-or-nothing: the notebook is saved only if every operation validates |

Batching is the point: `N` separate `nb_write_cell` calls read and rewrite the whole notebook `N` times, and a mid-batch failure leaves the file half-edited. `nb_batch_write_cells` validates every operation first, then applies them with a single save.

```json
{
  "notebook_path": "/path/to/nb.ipynb",
  "writes": [
    {"cell_id": 3, "source": "print('rewritten')"},
    {"cell_id": "a1b2c3d4", "source": "# rewritten by id"}
  ],
  "inserts": [
    {
      "after_cell_id": 7,
      "cells": [
        {"cell_type": "markdown", "source": "## Added section"},
        {"cell_type": "code", "source": "x = 1"}
      ]
    }
  ]
}
```

Insert anchors refer to the notebook as it was before the call, so a batch can insert at several anchors without tracking index shifts.

## Typical agent workflow

```
1. nb_metadata(path)              → Is this notebook big? What kernel?
2. nb_overview(path)              → See all cells at a glance (index, type, preview)
3. nb_headings(path)              → Understand section structure
4. nb_search(path, "pattern")     → Find cells containing a variable/function/import
5. nb_read_cell(path, 15)         → Read the specific cell you need
6. nb_read_cells(path, "15-20")   → Read a range of related cells
7. nb_read_section(path, "Results") → Read everything under a heading
8. nb_write_cell(path, 15, src)   → Edit the cell in-place
```

The key insight: **start with `nb_overview`, then drill down**. Never read the full notebook.

## Token economics

Tested against real project notebooks:

| Notebook | File size | Cells | Full `Read` tool | `nb_overview` | `nb_read_cell` | `nb_search` |
|---|---|---|---|---|---|---|
| NB00 (smallest) | 51 KB | 30 | ~13K tokens | ~500 tokens | ~50-200 tokens | ~100 tokens |
| NB01 (biggest) | 1.15 MB | 41 | ~294K tokens | ~690 tokens | ~100-400 tokens | ~50-200 tokens |

For the 1.15 MB notebook, `nb_overview` achieves **~425x token reduction** vs reading the full file. Individual cell reads achieve **~700-2900x reduction**.

## CLAUDE.md snippet

Add this to your project's `CLAUDE.md` to steer Claude Code toward using notebook-tools instead of built-in tools for `.ipynb` files. The server also ships its own `instructions` (injected into the system prompt automatically), but `CLAUDE.md` reinforcement ensures consistent behavior, especially when agents are choosing between several tools.

```markdown
### Working with .ipynb files

**ALWAYS use `notebook-tools` MCP tools instead of built-in tools for `.ipynb` files:**

| Task | Use this | NOT this | Why |
|------|----------|----------|-----|
| Read notebook | `nb_overview` then `nb_read_cell` | `Read` tool | Read loads raw JSON with base64 images, wastes 100K+ tokens |
| Search notebook | `nb_search` / `nb_search_dir` | `Grep` tool | Grep sees JSON structure, nb_search sees cell source code |
| Edit notebook cell | `nb_write_cell` (by index from nb_overview) | — | Consistent index-based workflow |
| Edit notebook cell | `NotebookEdit` (by cell_id) | — | Use when cell_id is known from another source |
| Insert/delete cells | `nb_insert_cell` / `nb_delete_cell` | — | Index-based, consistent with nb_overview |
| Edit many cells at once | `nb_batch_write_cells` | repeated `nb_write_cell` / `nb_insert_cell` | One load/save, all-or-nothing |

**Workflow:** `nb_overview` (get cell indices) → `nb_read_cell` or `nb_search` → `nb_write_cell`.

All 12 tools are in the `notebook-tools` MCP server. Start with `nb_overview` for any notebook interaction.
```

### When NotebookEdit is the better choice

The MCP write tools and Claude Code's built-in `NotebookEdit` solve the same problem (editing notebook cells) with different addressing:

- **MCP `nb_write_cell`**: addresses by integer index. Best when you're already in the `nb_overview` → `nb_read_cell` → edit flow, because you already have the index.
- **NotebookEdit**: addresses by `cell_id` (a string like `"abc123"`) or `cell_number` (0-indexed integer). Best when something else gives you the cell_id — for example, VS Code's notebook renderer, or the `id` field shown in `nb_read_cell` output.

In practice, MCP write tools are used more often because the typical agent workflow starts with `nb_overview`, which shows indices. `NotebookEdit` is better when the agent already has a `cell_id` from a non-MCP source, or when it needs `NotebookEdit`'s `edit_mode: "insert"` semantics (insert *after* a specific cell_id rather than *at* an index position).

Both tools can coexist safely. The server's `instructions` field tells agents to prefer MCP write tools during the `nb_overview` workflow. There is no conflict as long as the agent doesn't use both on the same cell in the same turn.

## Changelog

### v0.5.0 (2026-09-28)

- **Dependency:** Migrated to the MCP Python SDK v2 (`mcp>=2.1,<3`). v2 renamed `FastMCP` to `MCPServer` and removed `mcp.server.fastmcp` without a compatibility shim, so this version does not run on mcp 1.x. Stay on v0.4.0 with `mcp<2` if you need the 1.x line
- No behavior change: same 12 tools, same schemas, same `instructions`, same stdio transport

### v0.4.0 (2026-09-28)

- Added `nb_batch_write_cells`: overwrite and/or insert many cells in a single load/save, with all-or-nothing validation. Cell references accept an integer index or a cell `id` string
- Added `resolve_cell_index` to `_helpers.py` for shared index/cell-id resolution

### v0.3.0 (2026-02-25)

- **Fix:** Added `sort_keys=True` to `save_notebook` for deterministic JSON output matching Jupyter/nbformat convention
- **Agent guidance:** Added `FastMCP(instructions=...)` with tool selection decision tree (injected into agent system prompt)
- **Agent guidance:** Rewrote all 11 tool docstrings to specify when to use each tool vs built-in alternatives
- **Doc:** Documented write tools relationship to Claude Code's built-in NotebookEdit
- **Doc:** Added "How agents discover when to use these tools" section explaining the 3-channel guidance pattern

### v0.2.0 (2026-02-25)

- Added write tools: `nb_write_cell`, `nb_insert_cell`, `nb_delete_cell`
- Modularized into 6-file architecture
- Added `nb_headings`, `nb_read_section`, `nb_search_dir`

### v0.1.0

- Initial release: `nb_metadata`, `nb_overview`, `nb_read_cell`, `nb_read_cells`, `nb_search`
