"""Shared helpers for notebook-tools MCP server."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path


def load_notebook(path: str) -> dict:
    """Load and validate a notebook JSON file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Notebook not found: {path}")
    if p.suffix != ".ipynb":
        raise ValueError(f"Not a notebook file (expected .ipynb): {path}")
    try:
        with open(p, "r", encoding="utf-8") as f:
            nb = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in notebook: {e}")
    if "cells" not in nb:
        raise ValueError(f"Invalid notebook format: missing 'cells' key")
    return nb


def save_notebook(path: str, nb: dict) -> None:
    """Save notebook JSON with consistent formatting."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(nb, f, indent=1, ensure_ascii=False, sort_keys=True)
        f.write("\n")


def parse_cell_indices(spec: str, max_index: int) -> list[int]:
    """Parse '0,1,5-8' into [0, 1, 5, 6, 7, 8], clamped to valid range."""
    indices: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            tokens = part.split("-", 1)
            try:
                start = max(0, int(tokens[0].strip()))
                end = min(max_index, int(tokens[1].strip()))
            except ValueError:
                continue
            indices.extend(range(start, end + 1))
        else:
            try:
                idx = int(part)
                if 0 <= idx <= max_index:
                    indices.append(idx)
            except ValueError:
                continue
    return indices


def resolve_cell_index(cells: list[dict], ref: int | str) -> int:
    """Resolve a cell reference to a 0-based index.

    Accepts an integer index, or a string that is matched against the cells'
    'id' field first and only then parsed as an integer index.
    """
    if isinstance(ref, bool) or not isinstance(ref, (int, str)):
        raise ValueError(
            f"invalid cell reference {ref!r}: expected an integer index or a cell id string"
        )

    if isinstance(ref, int):
        if 0 <= ref < len(cells):
            return ref
        raise ValueError(f"cell index {ref} out of range (0-{len(cells) - 1})")

    for i, cell in enumerate(cells):
        if cell.get("id") == ref:
            return i

    try:
        idx = int(ref.strip())
    except ValueError:
        raise ValueError(f"cell id '{ref}' not found in notebook") from None
    if 0 <= idx < len(cells):
        return idx
    raise ValueError(f"cell index {idx} out of range (0-{len(cells) - 1})")


def get_cell_source(cell: dict) -> str:
    """Get cell source as a single string."""
    src = cell.get("source", "")
    if isinstance(src, list):
        return "".join(src)
    return str(src)


def format_output(output: dict, max_chars: int) -> str:
    """Extract text from a notebook output dict."""
    output_type = output.get("output_type", "")
    parts: list[str] = []

    if output_type == "stream":
        text = output.get("text", [])
        parts.append("".join(text) if isinstance(text, list) else str(text))

    elif output_type in ("execute_result", "display_data"):
        data = output.get("data", {})
        for mime in ("image/png", "image/jpeg", "image/svg+xml"):
            if mime in data:
                content = data[mime]
                if isinstance(content, list):
                    content = "".join(content)
                parts.append(f"[IMAGE: {mime}, {len(content)} chars base64]")
        if "text/plain" in data:
            text = data["text/plain"]
            parts.append("".join(text) if isinstance(text, list) else str(text))
        elif "text/html" in data:
            text = data["text/html"]
            parts.append("".join(text) if isinstance(text, list) else str(text))

    elif output_type == "error":
        traceback = output.get("traceback", [])
        parts.append("\n".join(traceback))

    result = "\n".join(parts)
    if len(result) > max_chars:
        result = result[:max_chars] + f"\n... [truncated, {len(result)} total chars]"
    return result


def format_cell(
    cell: dict,
    index: int,
    include_outputs: bool = False,
    max_output_chars: int = 2000,
) -> str:
    """Format a single cell for display. Shared by read_cell and read_cells."""
    ct = cell.get("cell_type", "unknown")
    src = get_cell_source(cell)
    n_lines = len(src.split("\n"))
    header = f"# Cell {index} ({ct}) | {n_lines} lines"
    parts = [header, src]

    if include_outputs and cell.get("outputs"):
        parts.append("\n--- OUTPUT ---")
        output_texts = [format_output(out, max_output_chars) for out in cell["outputs"]]
        combined = "\n".join(output_texts)
        if len(combined) > max_output_chars:
            combined = combined[:max_output_chars] + f"\n... [truncated, {len(combined)} total chars]"
        parts.append(combined)

    return "\n".join(parts)


def human_readable_size(n_bytes: int) -> str:
    """Convert bytes to '1.2 KB', '3.4 MB' etc."""
    if n_bytes < 1024:
        return f"{n_bytes} B"
    elif n_bytes < 1024 * 1024:
        return f"{n_bytes / 1024:.1f} KB"
    elif n_bytes < 1024 * 1024 * 1024:
        return f"{n_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{n_bytes / (1024 * 1024 * 1024):.1f} GB"


def output_byte_size(outputs: list[dict]) -> int:
    """Total serialized size of outputs in bytes."""
    return len(json.dumps(outputs).encode("utf-8")) if outputs else 0


def heading_level(text: str) -> int | None:
    """Return markdown heading level (1-6) or None if not a heading."""
    match = re.match(r"^(#{1,6})\s", text.strip())
    return len(match.group(1)) if match else None


def source_to_lines(source: str) -> list[str]:
    """Convert a source string to notebook list-of-lines format (with trailing \\n)."""
    lines = source.split("\n")
    if not lines:
        return [""]
    return [line + "\n" for line in lines[:-1]] + [lines[-1]]


def make_cell(cell_type: str, source: str) -> dict:
    """Create a minimal valid notebook cell."""
    cell = {
        "cell_type": cell_type,
        "metadata": {},
        "source": source_to_lines(source),
        "id": uuid.uuid4().hex[:8],
    }
    if cell_type == "code":
        cell["execution_count"] = None
        cell["outputs"] = []
    return cell


def find_notebooks(directory: str) -> list[Path]:
    """Find all .ipynb files in a directory (non-recursive, excludes checkpoints)."""
    d = Path(directory)
    if not d.is_dir():
        raise ValueError(f"Not a directory: {directory}")
    return sorted(
        p for p in d.glob("*.ipynb")
        if ".ipynb_checkpoints" not in str(p)
    )
