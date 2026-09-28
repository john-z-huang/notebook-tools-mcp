"""Write tools for notebook-tools MCP server.

Index-based counterparts to Claude Code's built-in NotebookEdit (which uses
cell_id/cell_number). These stay consistent with nb_overview/nb_read_cell indexing.
"""

from __future__ import annotations

from notebook_tools_mcp import mcp
from notebook_tools_mcp._helpers import (
    load_notebook,
    save_notebook,
    get_cell_source,
    make_cell,
    resolve_cell_index,
    source_to_lines,
)


@mcp.tool()
def nb_batch_write_cells(
    notebook_path: str,
    writes: list[dict] | None = None,
    inserts: list[dict] | None = None,
) -> str:
    """Batch write: overwrite and/or insert several cells in one load/save. Prefer this over repeated nb_write_cell/nb_insert_cell calls when editing many cells.

    writes: [{"cell_id": <index|id>, "source": "..."}] — overwrite existing cells.
    inserts: [{"after_cell_id": <index|id>, "cells": [{"cell_type": "code"|"markdown", "source": "..."}, ...]}] — insert cells directly after the anchor, in the order given.

    A cell reference is either a 0-based integer index (as shown by nb_overview) or a cell id string. All operations are validated before anything is applied, and the notebook is saved only if every one succeeds. Anchors resolve against the unchanged notebook, so insert order within a call does not shift other anchors."""
    if writes is None and inserts is None:
        return "Error: provide 'writes', 'inserts', or both"
    if writes is not None and not isinstance(writes, list):
        return "Error: 'writes' must be a list of {cell_id, source} objects"
    if inserts is not None and not isinstance(inserts, list):
        return "Error: 'inserts' must be a list of {after_cell_id, cells} objects"

    try:
        nb = load_notebook(notebook_path)
    except (FileNotFoundError, ValueError) as e:
        return f"Error: {e}"

    cells = nb["cells"]

    resolved_writes: list[tuple[int, str]] = []
    for i, spec in enumerate(writes or []):
        if not isinstance(spec, dict):
            return f"Error: writes[{i}] must be an object"
        if "cell_id" not in spec:
            return f"Error: writes[{i}] is missing 'cell_id'"
        if not isinstance(spec.get("source"), str):
            return f"Error: writes[{i}] is missing a string 'source'"
        try:
            resolved_writes.append((resolve_cell_index(cells, spec["cell_id"]), spec["source"]))
        except ValueError as e:
            return f"Error: writes[{i}]: {e}"

    resolved_inserts: list[tuple[int, list[dict]]] = []
    for i, spec in enumerate(inserts or []):
        if not isinstance(spec, dict):
            return f"Error: inserts[{i}] must be an object"
        if "after_cell_id" not in spec:
            return f"Error: inserts[{i}] is missing 'after_cell_id'"
        new_cells = spec.get("cells")
        if not isinstance(new_cells, list) or not new_cells:
            return f"Error: inserts[{i}].cells must be a non-empty list of {{cell_type, source}} objects"
        try:
            anchor = resolve_cell_index(cells, spec["after_cell_id"])
        except ValueError as e:
            return f"Error: inserts[{i}]: {e}"
        for j, new_cell in enumerate(new_cells):
            if not isinstance(new_cell, dict):
                return f"Error: inserts[{i}].cells[{j}] must be an object"
            if new_cell.get("cell_type") not in ("code", "markdown"):
                return (
                    f"Error: inserts[{i}].cells[{j}]: cell_type must be 'code' or 'markdown', "
                    f"got {new_cell.get('cell_type')!r}"
                )
            if not isinstance(new_cell.get("source"), str):
                return f"Error: inserts[{i}].cells[{j}] is missing a string 'source'"
        resolved_inserts.append((anchor, new_cells))

    for index, source in resolved_writes:
        cells[index]["source"] = source_to_lines(source)

    by_anchor: dict[int, list[list[dict]]] = {}
    for anchor, new_cells in resolved_inserts:
        by_anchor.setdefault(anchor, []).append(new_cells)

    # Descending anchor order so that insertions never shift an anchor still to be processed.
    for anchor in sorted(by_anchor, reverse=True):
        batch: list[dict] = []
        for new_cells in by_anchor[anchor]:
            batch.extend(make_cell(c["cell_type"], c["source"]) for c in new_cells)
        cells[anchor + 1 : anchor + 1] = batch

    try:
        save_notebook(notebook_path, nb)
    except OSError as e:
        return f"Error saving notebook: {e}"

    parts: list[str] = []
    if resolved_writes:
        indices = ", ".join(str(index) for index, _ in resolved_writes)
        parts.append(f"{len(resolved_writes)} overwritten (index {indices})")
    if resolved_inserts:
        n_inserted = sum(len(new_cells) for _, new_cells in resolved_inserts)
        anchors = ", ".join(str(anchor) for anchor, _ in resolved_inserts)
        parts.append(f"{n_inserted} inserted (after index {anchors})")
    return f"Batch write to {notebook_path}: {'; '.join(parts)}. {len(cells)} cells total."


@mcp.tool()
def nb_write_cell(notebook_path: str, cell_index: int, source: str) -> str:
    """Overwrite cell source by index (from nb_overview). All notebook-tools use positional indices, not cell IDs. Prefer this over NotebookEdit when working within the nb_overview workflow."""
    try:
        nb = load_notebook(notebook_path)
    except (FileNotFoundError, ValueError) as e:
        return f"Error: {e}"

    cells = nb["cells"]
    if cell_index < 0 or cell_index >= len(cells):
        return f"Error: cell_index {cell_index} out of range (0-{len(cells) - 1})"

    cells[cell_index]["source"] = source_to_lines(source)

    try:
        save_notebook(notebook_path, nb)
    except OSError as e:
        return f"Error saving notebook: {e}"

    n_lines = len(source.split("\n"))
    n_chars = len(source)
    return f"Cell {cell_index} updated ({n_lines} lines, {n_chars} chars)"


@mcp.tool()
def nb_insert_cell(notebook_path: str, cell_index: int, cell_type: str, source: str) -> str:
    """Insert a new cell at position (use cell_index=-1 to append). Cell type must be 'code' or 'markdown'. Indices of subsequent cells shift by +1."""
    if cell_type not in ("code", "markdown"):
        return f"Error: cell_type must be 'code' or 'markdown', got '{cell_type}'"

    try:
        nb = load_notebook(notebook_path)
    except (FileNotFoundError, ValueError) as e:
        return f"Error: {e}"

    cells = nb["cells"]
    n_cells = len(cells)

    if cell_index == -1:
        actual_index = n_cells
    elif 0 <= cell_index <= n_cells:
        actual_index = cell_index
    else:
        return f"Error: cell_index {cell_index} out of range (-1 or 0-{n_cells})"

    cell = make_cell(cell_type, source)
    cells.insert(actual_index, cell)

    try:
        save_notebook(notebook_path, nb)
    except OSError as e:
        return f"Error saving notebook: {e}"

    total = len(cells)
    return f"Inserted {cell_type} cell at index {actual_index} ({total} cells total)"


@mcp.tool()
def nb_delete_cell(notebook_path: str, cell_index: int) -> str:
    """Delete a cell by index. Returns the first line of the deleted cell for confirmation. Indices of subsequent cells shift by -1."""
    try:
        nb = load_notebook(notebook_path)
    except (FileNotFoundError, ValueError) as e:
        return f"Error: {e}"

    cells = nb["cells"]
    if cell_index < 0 or cell_index >= len(cells):
        return f"Error: cell_index {cell_index} out of range (0-{len(cells) - 1})"

    cell = cells[cell_index]
    cell_type = cell.get("cell_type", "unknown")
    src = get_cell_source(cell)
    first_line = src.split("\n")[0].rstrip() if src else ""
    if len(first_line) > 60:
        first_line = first_line[:57] + "..."

    del cells[cell_index]

    try:
        save_notebook(notebook_path, nb)
    except OSError as e:
        return f"Error saving notebook: {e}"

    remaining = len(cells)
    return f"Deleted cell {cell_index} ({cell_type}: {first_line}). {remaining} cells remaining."
