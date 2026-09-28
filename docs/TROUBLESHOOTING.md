# Troubleshooting: notebook-tools-mcp

## MCP tools denied in subagents / autonomous agents

### Symptoms

- `nb_search`, `nb_read_cell`, `nb_write_cell` etc. return "denied" or are silently skipped
- `nb_overview` might work (if it was the only tool you manually approved once) but all others fail
- Subagents (Task tool agents, background agents) fail on notebook tools while the main conversation works fine
- Agent logs show tool calls were auto-denied without user prompt

### Cause

Claude Code requires explicit permission for MCP tools. The main conversation can prompt you interactively ("Allow `mcp__notebook-tools__nb_search`?"), but **subagents cannot prompt** — they run autonomously, so any unapproved tool is auto-denied.

Permissions live in `.claude/settings.local.json` under `permissions.allow`. Each MCP tool needs an entry in the format `mcp__<server-name>__<tool-name>`. If your `settings.local.json` doesn't list all 12 notebook-tools, subagents can't use them.

### Fix: Manual setup

**1. Find your settings file:**

```bash
# Project-level (most common)
cat .claude/settings.local.json

# If it doesn't exist, create the directory
mkdir -p .claude
```

**2. Add all 12 tool permissions to `permissions.allow`:**

```json
{
  "permissions": {
    "allow": [
      "mcp__notebook-tools__nb_metadata",
      "mcp__notebook-tools__nb_overview",
      "mcp__notebook-tools__nb_read_cell",
      "mcp__notebook-tools__nb_read_cells",
      "mcp__notebook-tools__nb_read_section",
      "mcp__notebook-tools__nb_headings",
      "mcp__notebook-tools__nb_search",
      "mcp__notebook-tools__nb_search_dir",
      "mcp__notebook-tools__nb_write_cell",
      "mcp__notebook-tools__nb_insert_cell",
      "mcp__notebook-tools__nb_delete_cell",
      "mcp__notebook-tools__nb_batch_write_cells"
    ],
    "deny": []
  }
}
```

If you already have other entries in `permissions.allow` (e.g. `Bash(*)`, `Read(*)`), append the `mcp__notebook-tools__*` entries to the existing array. Don't replace the whole file.

**3. Restart Claude Code:**

```bash
exit    # or Ctrl+D
claude  # restart
```

**4. Verify:**

In a new conversation, run `/mcp` to confirm `notebook-tools` shows as connected. Then test a subagent:

```
Use the Task tool to read cell 0 of /path/to/notebook.ipynb using nb_read_cell
```

If the subagent succeeds, permissions are working.

### Fix: SciAgent-toolkit users

If you use [SciAgent-toolkit](https://github.com/tony-zhelonkin/SciAgent-toolkit), the addon system handles permissions automatically:

```bash
# This adds all 12 permissions to settings.local.json
./scripts/manage-addon.sh enable notebook-tools --project-dir /path/to/project
```

The `tool_permissions` array in `notebook-tools.addon.json` declares all 11 tools. `manage-addon.sh enable` reads this array and merges the entries into `settings.local.json`. Disabling the addon removes them. Profile switches (`switch-mcp-profile.sh`) preserve addon permissions.

See SciAgent-toolkit's [TROUBLESHOOTING.md](https://github.com/tony-zhelonkin/SciAgent-toolkit/blob/main/docs/TROUBLESHOOTING.md) for the full architecture of how addon permissions flow.

### Why this happens

Claude Code's permission model is designed for interactive use. MCP tools are "deferred" — they're not loaded until needed, and the first use triggers a permission prompt. This works in the main conversation where the user can click "Allow". But the Task tool (subagents) runs headless — no user present to approve. If the tool isn't pre-approved in `settings.local.json`, it's denied.

This is not a bug in notebook-tools-mcp. It's a property of Claude Code's security model. The fix is always the same: pre-approve tools in `settings.local.json` before using them in subagents.

---

## Server not starting / "Failed to connect"

### Symptoms

- `/mcp` shows `notebook-tools` with a red status
- Error: `ModuleNotFoundError: No module named 'notebook_tools_mcp'`

### Fix

```bash
# Check the package is installed in the Python that Claude Code uses
python -m notebook_tools_mcp.server  # should print nothing and wait for stdin

# If not found, install it
pip install git+https://github.com/tony-zhelonkin/notebook-tools-mcp.git

# Or for a local editable install
pip install -e /path/to/notebook-tools-mcp/
```

Make sure the `python` in your `.mcp.json` command matches the Python where the package is installed. In a venv:

```json
{
  "mcpServers": {
    "notebook-tools": {
      "type": "stdio",
      "command": "/path/to/venv/bin/python",
      "args": ["-m", "notebook_tools_mcp.server"]
    }
  }
}
```

---

## Changes not taking effect after editing source

### Symptoms

- You edited `_helpers.py` or a tool file, but the MCP server still uses old behavior
- `sort_keys=True` not producing sorted output (as seen during v0.3 development)

### Cause

MCP stdio servers are spawned as separate processes by the MCP client. If the server was started before your edit (or if the installed package differs from your working copy), it uses the old code.

### Fix

1. Restart Claude Code (this restarts all MCP servers)
2. If using an editable install (`pip install -e .`), ensure the working copy is the installed one:
   ```bash
   python -c "import notebook_tools_mcp; print(notebook_tools_mcp.__file__)"
   ```
3. If using a non-editable install, reinstall:
   ```bash
   pip install --force-reinstall git+https://github.com/tony-zhelonkin/notebook-tools-mcp.git
   ```

---

## nb_read_section returns unexpected cells

### Symptoms

- `nb_read_section(path, "Results")` returns too many or too few cells
- Section boundary detection seems wrong

### Cause

`nb_read_section` relies on markdown heading hierarchy (`#`, `##`, `###`). It reads from the matched heading until the next heading at the same or higher level. If a notebook has inconsistent heading levels (e.g. jumps from `#` to `###` with no `##`), boundaries may not match expectations.

### Workaround

Use `nb_headings` to see the actual heading structure, then use explicit `nb_read_cells("15-25")` ranges instead of `nb_read_section`. The `max_cells` parameter also acts as a safety limit.

---

## Write tools produce noisy git diffs

### Cause (fixed in v0.3.0)

Before v0.3.0, `save_notebook` did not use `sort_keys=True`, so JSON key order could change between load/save cycles. This was fixed in v0.3.0.

### Fix

Update to v0.3.0+:

```bash
pip install --upgrade git+https://github.com/tony-zhelonkin/notebook-tools-mcp.git
```
