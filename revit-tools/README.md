# revit-tools

> Query a live Revit 2027 model through an AI chat — no cloud, no API keys, one file.
> **Experimental proof of concept. Not production software.**

---

## What it is

`revit-tools` is a single-file, standard-library-only Python MCP server that bridges an AI assistant to a running Revit 2027 model. It spawns Autodesk's official `Autodesk.RevitMcpServer.Stdio.exe` as a child process and adds a deterministic audit suite on top.

**15 MCP tools:**
- **7 native Autodesk tools** — `query_model`, `get_element_data`, `export_views` (schedules to CSV), `open_view`, `select_elements`, `zoom_to_elements`, `get_running_revit_instances`
- **8 deterministic audit tools** — floor area, lot area (shoelace formula), lot coverage, septic, energy, WWR, setback. Pure math, no LLM guesswork.

**Key properties:**
- **Read-only and fully local.** Nothing is written to the model. No data leaves the machine.
- **Deterministic math.** The audit tools compute numbers from the model's geometry. When data is absent, the tool says "not in the model" instead of inventing a figure.
- **Auto-discovers the running Revit instance.** Detects the first process ID and injects `revitInstanceId` into every call so the agent doesn't have to manage it by hand.
- **Zero external dependencies.** Python standard library only — no `pip install`, no `requirements.txt`, no `.env`, no pywin32.

---

## Prerequisites

- **Windows** (the Revit MCP add-in runs on Windows only)
- **Revit 2027** with the [**Revit MCP Server Read-Tools Technical Preview**](https://www.autodesk.com/) add-in installed, a model open
- **Python 3.9 or later** (any CPython — the server is stdlib-only)
- An **MCP client** — either [DeepSeek Harness](https://deepseek.com/) (DSH) or any other stdio MCP client (Claude Desktop, Continue, etc.)

---

## Installation

### Option A: DeepSeek Harness (preset)

The `revit-tools` folder is a self-contained DSH preset. Copy it to your DSH agent-presets directory:

```powershell
# Copy the entire folder to your DSH presets
copy .\revit-tools\ %USERPROFILE%\.dsh\.agent-presets\revit-tools\
```

Then edit `%USERPROFILE%\.dsh\.agent-presets\revit-tools\agent.cordis.yml` and fix **three paths**:

```yaml
- id: mcp-revit-tools
  name: '@deepseek-ai/dsh-mcp-client'
  config:
    serverName: revit-tools
    transport: stdio
    command: 'python'   # <-- the target machine's Python (or full path)
    cwd: '<PRESET-FOLDER-PATH>'   # <-- where you copied the folder
    args:
      - 'axo_mcp_server.py'
      - '<EXE-PATH>'   # <-- path to Autodesk.RevitMcpServer.Stdio.exe
    toolCallTimeoutMs: 300000
```

The Autodesk exe is installed at:

```
C:\Program Files\Autodesk\Revit 2027 MCP Server Read-Tools Technical Preview\Autodesk.RevitMcpServer.Stdio.exe
```

Start a new DSH session on the **Revit Tools** preset. The 15 tools will appear as `mcp__revit_tools__*`.

### Option B: Any MCP client (standalone)

If you use a different MCP client (Claude Desktop, Continue, Cursor, etc.), point it directly at the server:

```json
{
  "mcpServers": {
    "revit-tools": {
      "command": "python",
      "args": [
        "path/to/axo_mcp_server.py",
        "path/to/Autodesk.RevitMcpServer.Stdio.exe"
      ],
      "cwd": "path/to/preset-folder"
    }
  }
}
```

The server runs on standard I/O — no network ports, no firewall changes.

---

## How to use

Once your MCP client has discovered the tools, ask in plain English:

| You say | What runs |
|---|---|
| "Total floor area per level" | `axo_audit_floor_area` |
| "What's the lot area and building lot coverage?" | `axo_audit_lot_area` + `axo_audit_lot_coverage` |
| "Export the door and window schedules to CSV" | `get_running_revit_instances` → `export_views` |
| "Window-to-wall ratio, septic clearances, energy envelope" | `axo_audit_wwr`, `axo_audit_septic`, `axo_audit_energy` |
| "List all walls on level 1 with dimensions" | `query_model`(OST_Walls) → `get_element_data` |
| "Which Revit documents are open?" | `get_running_revit_instances` |

Explicit tool names (DSH): `mcp__revit_tools__query_model`, `mcp__revit_tools__axo_audit_floor_area`, etc.

---

## Available tools

### Native Autodesk (pass-through)

| Tool | Purpose |
|---|---|
| `get_running_revit_instances` | Lists open Revit processes with active/linked documents |
| `query_model` | Query elements by category, returns element IDs |
| `get_element_data` | Retrieve detailed parameters for given element IDs |
| `export_views` | Export schedules to CSV file |
| `open_view` | Navigate to a view in Revit |
| `select_elements` | Highlight elements in the Revit UI |
| `zoom_to_elements` | Focus the camera on selected elements |

### Axoworks audit tools (deterministic)

| Tool | What it computes |
|---|---|
| `axo_audit_floor_area` | Room-based floor area by level, with optional level filter |
| `axo_query_floor_area` | OST_Floors element areas; maximum single-level plate = building footprint |
| `axo_audit_lot_area` | Lot area from OST_SiteProperty via shoelace formula; sq ft and acres |
| `axo_audit_lot_coverage` | Building footprint ÷ lot area × 100 (composite of the two above) |
| `axo_audit_septic` | Counts plumbing fixtures and property lines (distances pending add-in update) |
| `axo_audit_energy` | Energy envelope stub (placeholder — parity with original engine) |
| `axo_audit_wwr` | Window-to-wall ratio count (area ratio pending add-in geometry) |
| `axo_audit_setback` | Setback distance stub (property-line geometry not exported by add-in) |

> Audit tools marked "placeholder" return honest narratives about what they could and could not compute. They never invent a number.

---

## Architecture

```
MCP client (DSH, Claude Desktop, etc.)
  │
  └─ stdio ──▶ axo_mcp_server.py  (one file, Python stdlib only)
                  │
                  ├─ child stdio ──▶ Autodesk.RevitMcpServer.Stdio.exe
                  │                     │
                  │                     └─ named pipe ──▶ MCP add-in inside Revit 2027
                  │
                  └─ adds the 8 axo_* audit tools (deterministic math over native surface)
```

The server serializes all upstream calls, applies per-call timeouts, and auto-injects the `revitInstanceId` parameter.

---

## Limitations

These come from the Autodesk Revit MCP Server 2027 Technical Preview and apply to any client built on it:

1. **Single-threaded.** Every query queues on Revit's UI thread. Rapid-fire calls or retry loops can **permanently deadlock** the MCP connection (symptom: `tools/list` answers, `query_model` hangs forever). The only cure is restarting the add-in or Revit. **One query at a time, stop on error, never retry-storm.**
2. **Read-only, host model only.** Linked models are visible in `get_running_revit_instances` but cannot be queried.
3. **`searchScope` discipline.** Always pass `"searchScope": "AllViews"` in `query_model` — the server defaults to the active view and returns empty lists otherwise.
4. **`OST_Roofs` can hang.** On complex models, test with `maxResults: 1` before larger roof queries.
5. **Geometry not fully exposed.** Property-line geometry is not exported, so setback distances and true window-to-wall area ratios are not derivable. Energy U-factor/SHGC extraction is also a placeholder. These are honest "unavailable" narratives, not errors.
6. **Heavy queries are slow.** 30–60+ seconds for large extractions is normal. Budget a generous tool timeout (5 minutes in the default config).
7. **No governance layer.** The server serializes calls and applies timeouts, but does not deduplicate, heartbeat, or re-audit payloads. The *agent* must be disciplined: stop on error, do not retry blindly.

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| No tools appear in session | MCP client not connected to the server. Verify the `command` and `args` paths. |
| `tools/list` OK but all queries hang | Main-thread deadlock (limitation #1). Restart the MCP add-in or Revit. |
| `get_running_revit_instances` → `[]` | Pipe attach in flight. The add-in connects ~2–3 seconds after first contact; call it again. |
| `query_model` returns empty `{ "levels": [] }` | Missing `"searchScope": "AllViews"` in the call. |
| Audit tools report "no rooms" / "0 sq ft" | Data gap in the model (rooms not placed, Area unpopulated), not a connection problem. |
| Tool call times out | Complex model; budget 5 minutes. Do **not** loop-retry (limitation #1). |

---

## Comparison with other routes

Two other configurations exist on the same machine for reference:

- **`revit` (proxy):** The original Axoworks middleware — Python proxy with governance, coordinate translation, and the same audit suite. Requires the `revitmcp` repo, venv, and pip dependencies.
- **`revit-direct` (bare):** Launches the Autodesk exe directly. Zero Python, 7 native tools, no audit suite. No instance auto-injection — the agent must manage `revitInstanceId` manually.

All three use distinct `serverName` values and can coexist in the same DSH process without collision.

---

## License

This project is open source under the MIT License.

> **Disclaimer:** This is an experimental QA/QC reference tool. It is **not** professional architectural, engineering, or legal advice, and it is not a substitute for the judgment of a licensed Architect or Engineer of Record. Building codes are subject to localized interpretations, exceptions, and updates — verify every audit result with a qualified professional before relying on it.