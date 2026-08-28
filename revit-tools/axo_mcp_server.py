#!/usr/bin/env python3
"""
Axoworks REVIT-TOOLS — single-file MCP server (Option B)
==========================================================
An MCP stdio server that:

  1. Spawns Autodesk's official ``Autodesk.RevitMcpServer.Stdio.exe`` as a child
     (upstream), forwards its native tools transparently, and self-heals it
     (respawns + re-initializes) if the child exits.
  2. Adds the Axoworks ``axo_*`` audit tools — deterministic math over the
     native ``query_model`` / ``get_element_data`` surface (ported from
     ``revitmcp/audit_tools.py`` + ``mcp_parsers.py``).
  3. Discovers the connected Revit instance (processId) and injects
     ``revitInstanceId`` into internal calls when the client omits it.

Zero external dependencies — Python standard library only (run with any
CPython 3.9+). The venv/pip stack from the original middleware is NOT needed.

Usage:
    python axo_mcp_server.py [path-to-Autodesk.RevitMcpServer.Stdio.exe]

Portability: the exe path is a single argv (or DEFAULT_EXE). Revit + the
MCP add-in must be running; the exe finds the named pipe itself.

Discipline (from the engine's own readme): Revit's main thread is single —
call sites must stop on error and never rapid-fire. This server serializes
all upstream calls and applies one timeout per internal call; it does NOT
retry on the agent's behalf.
"""
from __future__ import annotations

import json
import logging
import queue
import re
import subprocess
import sys
import threading
import time
from collections import defaultdict  # (audit_tools.py was missing this import)
from typing import Any

DEFAULT_EXE = (
    r"C:\Program Files\Autodesk\Revit 2027 MCP Server Read-Tools Technical "
    r"Preview\Autodesk.RevitMcpServer.Stdio.exe"
)
PROTOCOL_VERSION = "2025-06-18"
UPSTREAM_CALL_TIMEOUT_S = 120.0
SERVER_NAME = "axoworks-revit-tools"
SERVER_VERSION = "1.0.0"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
                    stream=sys.stderr)
log = logging.getLogger("axo-mcp-server")


# ===========================================================================
# Parsing helpers (ported from revitmcp/mcp_parsers.py — handles all known
# Autodesk response shapes, with regex fallbacks)
# ===========================================================================

def pick(params: dict, keys: list) -> Any:
    for k in keys:
        if k in params:
            v = params[k]
            return v.get("value") if isinstance(v, dict) else v
    return None


def get_raw_text(raw_resp: Any) -> str:
    if not isinstance(raw_resp, dict):
        return json.dumps(raw_resp, default=str) if raw_resp else ""
    for itm in raw_resp.get("content", []):
        if isinstance(itm, dict) and itm.get("type") == "text":
            return itm.get("text", "")
    return json.dumps(raw_resp, default=str)


def extract_element_ids(raw_resp: Any) -> list:
    ids: list = []
    text = get_raw_text(raw_resp)
    if not text:
        return ids
    try:
        parsed = json.loads(text)
        for el in parsed.get("outcome", {}).get("elements", []):
            eid = (el or {}).get("elementId") or (el or {}).get("id")
            if eid is not None:
                ids.append(int(eid))
        if not ids:
            for el in parsed.get("elements", []):
                eid = (el or {}).get("elementId") or (el or {}).get("id")
                if eid is not None:
                    ids.append(int(eid))
        if not ids:
            r = parsed.get("results", {})
            if isinstance(r, dict):
                ids = [int(x) for x in r.get("Element Ids", []) if x]
            elif isinstance(r, list):
                ids = [int(x) for x in r if x]
        if not ids and "Element Ids" in parsed:
            ids = [int(x) for x in parsed["Element Ids"] if x]
    except Exception:
        pass
    if not ids:
        ids = [int(m) for m in re.findall(r"\b(\d{6,8})\b", text)]
    return ids


def extract_elements(raw_resp: Any) -> list:
    text = get_raw_text(raw_resp)
    if not text:
        return []
    try:
        parsed = json.loads(text)
        if "elements" in parsed and isinstance(parsed["elements"], list):
            return parsed["elements"]
        out_e = parsed.get("outcome", {}).get("elements", [])
        if out_e:
            return out_e
        results = parsed.get("results", {})
        if isinstance(results, dict) and "Element Ids" not in results:
            elems = [v for v in results.values() if isinstance(v, dict)]
            if elems:
                return elems
    except Exception:
        pass
    return []


def extract_number(val: Any) -> float:
    if isinstance(val, (int, float)):
        return float(val)
    match = re.search(r"-?\d+\.?\d*", str(val).replace(",", ""))
    if match:
        return float(match.group())
    raise ValueError(f"Could not extract number from {val}")


def try_parse_float(val: Any, default: float = 0.0) -> float:
    try:
        return extract_number(val)
    except (ValueError, TypeError, AttributeError):
        return default


AREA_KEYS = ["Area", "area", "PROPERTY_LINE_AREA", "SITE_PROPERTY_LINE_AREA",
             "ROOM_AREA", "GSA_SPACE_AREA", "NetArea", "GrossArea", "AREA"]
NAME_KEYS = ["Name", "Mark", "Comments", "ELEM_TYPE_PARAM", "Type Name", "Family"]
LEVEL_KEYS = ["Level", "level", "LEVEL_PARAM"]


# ===========================================================================
# Upstream: Autodesk.RevitMcpServer.Stdio.exe, managed as an MCP child client
# ===========================================================================

class UpstreamError(Exception):
    pass


class Upstream:
    def __init__(self, exe_path: str):
        self.exe = exe_path
        self.proc: subprocess.Popen | None = None
        self.out_q: "queue.Queue[str]" = queue.Queue()
        self.err_tail: list = []
        self._rid = 0
        self._lock = threading.RLock()  # reentrant: ensure() -> _rpc() re-acquires
        self._initialized = False
        self.tools_cache: list | None = None
        self.instance_id: int | None = None

    # -- lifecycle ----------------------------------------------------------

    def _spawn(self) -> None:
        log.info("spawning upstream: %s", self.exe)
        self.proc = subprocess.Popen(
            [self.exe],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.out_q = queue.Queue()
        threading.Thread(target=self._reader, daemon=True).start()
        threading.Thread(target=self._err_reader, daemon=True).start()

    def _reader(self) -> None:
        assert self.proc and self.proc.stdout
        for line in iter(self.proc.stdout.readline, b""):
            self.out_q.put(line.decode("utf-8", "replace"))

    def _err_reader(self) -> None:
        assert self.proc and self.proc.stderr
        for line in iter(self.proc.stderr.readline, b""):
            if len(self.err_tail) < 40:
                self.err_tail.append(line.decode("utf-8", "replace").rstrip())

    def _send(self, obj: dict) -> None:
        assert self.proc and self.proc.stdin
        self.proc.stdin.write((json.dumps(obj) + "\n").encode("utf-8"))
        self.proc.stdin.flush()

    def _wait_for(self, rid: int, timeout_s: float) -> dict:
        deadline = time.time() + timeout_s
        while True:
            try:
                line = self.out_q.get(timeout=0.3)
            except queue.Empty:
                if self.proc is None or self.proc.poll() is not None:
                    code = self.proc.poll() if self.proc else None
                    tail = " | ".join(self.err_tail[-4:])
                    raise UpstreamError(f"upstream Autodesk server exited (code {code}). {tail}")
                if time.time() > deadline:
                    raise UpstreamError(f"upstream call timed out after {timeout_s:.0f}s")
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("id") == rid:
                return d

    def _rpc(self, method: str, params: dict, timeout_s: float) -> dict:
        with self._lock:
            self._rid += 1
            rid = self._rid
            self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
            d = self._wait_for(rid, timeout_s)
            if "error" in d:
                raise UpstreamError(f"upstream RPC error for {method}: {d['error']}")
            return d

    def ensure(self) -> None:
        """Respawn if dead; run the MCP handshake once per child."""
        with self._lock:
            if self.proc is None or self.proc.poll() is not None:
                self._initialized = False
                self.tools_cache = None
                self.err_tail = []
                if not (self.proc is not None and self.proc.poll() is None):
                    self._spawn()
            if not self._initialized:
                d = self._rpc("initialize", {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                }, 30.0)
                self._initialized = True
                p = d.get("result", {}).get("params") or d.get("result", {})
                self.instance_id = None
                try:
                    self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
                except Exception:
                    pass
                log.info("upstream initialized")

    # -- MCP surface ---------------------------------------------------------

    def list_tools(self) -> list:
        self.ensure()
        if self.tools_cache is None:
            d = self._rpc("tools/list", {}, 60.0)
            self.tools_cache = d.get("result", {}).get("tools", [])
        return self.tools_cache

    def discover_instance(self, timeout_s: float = 20.0,
                          interval_s: float = 1.5) -> int | None:
        """Trigger attachment to the add-in pipe; poll until an instance appears.

        The add-in's ConnectionManager attaches asynchronously after the first
        tool call, so a single ``get_running_revit_instances`` may return ``[]``
        for a few seconds. We poll until a PID shows up or *timeout_s* elapses.
        """
        if self.instance_id is not None:
            return self.instance_id
        deadline = time.time() + timeout_s
        while True:
            try:
                self.ensure()
                with self._lock:
                    self._rid += 1
                    rid = self._rid
                    self._send({"jsonrpc": "2.0", "id": rid, "method": "tools/call",
                                "params": {"name": "get_running_revit_instances",
                                           "arguments": {}}})
                    d = self._wait_for(rid, 30.0)
            except UpstreamError as e:
                log.warning("instance discovery attempt failed: %s", e)
            else:
                text = get_raw_text(d.get("result", {}))
                try:
                    data = json.loads(text)
                except Exception:
                    data = None
                if isinstance(data, list) and data:
                    rec = data[0] if isinstance(data[0], dict) else {}
                    pid = rec.get("processId") or rec.get("ProcessId")
                    if pid is not None:
                        self.instance_id = int(pid)
                        log.info("attached Revit instance pid=%s", self.instance_id)
                        return self.instance_id
            if self.instance_id is not None:
                return self.instance_id
            if time.time() >= deadline:
                return None
            time.sleep(interval_s)

    def call_tool(self, name: str, arguments: dict,
                  timeout_s: float = UPSTREAM_CALL_TIMEOUT_S,
                  inject_instance: bool = True) -> dict:
        self.ensure()
        if inject_instance and isinstance(arguments, dict) and "revitInstanceId" not in arguments:
            iid = self.discover_instance()
            if iid is None:
                raise UpstreamError(
                    "No running Revit instance was detected. Confirm Revit is open with "
                    "the MCP add-in active, then retry. (The add-in attaches a few "
                    "seconds after first contact.)")
            arguments = {**arguments, "revitInstanceId": iid}
        d = self._rpc("tools/call", {"name": name, "arguments": arguments}, timeout_s)
        return d.get("result", {})


# ===========================================================================
# Axoworks audit tools (ported from revitmcp/audit_tools.py; the async/governor
# scaffolding is replaced with synchronous calls through Upstream)
# ===========================================================================

def run_floor_area_audit(up: Upstream, arguments: dict) -> dict:
    level_names = arguments.get("level_names")
    include_room_details = arguments.get("include_room_details", True)
    try:
        rooms_raw = up.call_tool("query_model", {
            "input": {"categories": ["OST_Rooms"], "searchScope": "AllViews", "maxResults": 500}})
    except UpstreamError as exc:
        return {"error": f"Failed to query Revit model rooms: {exc}"}

    room_ids = extract_element_ids(rooms_raw)
    if not room_ids:
        return {
            "audit_type": "floor_area",
            "total_rooms_found": 0,
            "narrative": ("No rooms found in the Revit model. Ensure rooms are placed on "
                          "floor plans (Room elements, not just spaces)."),
            "levels": [],
        }

    room_details = []
    try:
        data_raw = up.call_tool("get_element_data", {
            "elementIds": [int(e) for e in room_ids],
            "outputOptions": {"basicElementInfo": True, "parametersOutputType": "KeyParameters"}})
        for elem in extract_elements(data_raw):
            if not isinstance(elem, dict):
                continue
            params = elem.get("parameters", {})
            eid = elem.get("elementId") or elem.get("id", "?")
            area_val = pick(params, AREA_KEYS) or pick(elem, AREA_KEYS)
            level_val = (pick(params, LEVEL_KEYS) or pick(elem, LEVEL_KEYS)
                         or elem.get("level") or "Unknown Level")
            name_val = (elem.get("name") or pick(params, ["Name", "Mark", "Type Name", "Family"])
                        or pick(elem, ["Name", "Mark", "Type Name", "Family"]) or "Unnamed")
            number_val = pick(params, ["Number", "number"]) or elem.get("number") or ""
            room_details.append({
                "element_id": eid,
                "name": name_val,
                "number": str(number_val),
                "level": level_val,
                "area": try_parse_float(area_val, 0.0),
                "area_unit": "sq ft",
            })
    except UpstreamError:
        pass  # room_details stays empty — returns zeros below

    levels_map: dict = {}
    for rd in room_details:
        level_name = rd.get("level") or "Unknown Level"
        if level_names and level_name not in level_names:
            continue
        if level_name not in levels_map:
            levels_map[level_name] = {"level_name": level_name, "total_rooms": 0,
                                      "total_area_sqft": 0.0, "rooms": []}
        levels_map[level_name]["total_rooms"] += 1
        levels_map[level_name]["total_area_sqft"] += rd["area"]
        if include_room_details:
            levels_map[level_name]["rooms"].append(
                {"name": rd["name"], "number": rd["number"], "area_sqft": round(rd["area"], 2)})

    level_summaries = []
    for lv in sorted(levels_map.values(), key=lambda x: x["level_name"]):
        entry = {"level_name": lv["level_name"], "total_rooms": lv["total_rooms"],
                 "total_area_sqft": round(lv["total_area_sqft"], 2)}
        if include_room_details and lv["rooms"]:
            entry["rooms"] = sorted(lv["rooms"], key=lambda r: r["name"])
        level_summaries.append(entry)

    grand_total = round(sum(lv["total_area_sqft"] for lv in levels_map.values()), 2)
    total_rooms = sum(lv["total_rooms"] for lv in levels_map.values())
    parts = ([f"Floor area audit filtered to {len(level_summaries)} level(s): "
              f"{', '.join(level_names)}."] if level_names
             else [f"Floor area audit across {len(level_summaries)} level(s)."])
    parts.append(f"Total floor area: {grand_total:,} sq ft across {total_rooms} room(s).")
    for lv in level_summaries:
        parts.append(f"  - {lv['level_name']}: {lv['total_area_sqft']:,} sq ft ({lv['total_rooms']} room(s))")

    return {"audit_type": "floor_area", "total_rooms_found": total_rooms,
            "grand_total_area_sqft": grand_total, "levels": level_summaries,
            "narrative": "\n".join(parts)}


def run_floor_area_query(up: Upstream, arguments: dict) -> dict:
    level_names = arguments.get("level_names")
    include_details = arguments.get("include_details", True)
    try:
        raw = up.call_tool("query_model", {
            "input": {"categories": ["OST_Floors"], "searchScope": "AllViews", "maxResults": 200}})
        floor_ids = extract_element_ids(raw)
        if not floor_ids:
            return {"audit_type": "floor_area_query", "status": "Unavailable",
                    "narrative": "No OST_Floors elements found in the model.",
                    "building_footprint_sqft": 0.0, "levels": []}

        data_raw = up.call_tool("get_element_data", {
            "elementIds": [int(e) for e in floor_ids],
            "outputOptions": {"basicElementInfo": True, "parametersOutputType": "AllParameters"}})
        floor_details = []
        for ev in extract_elements(data_raw):
            if not isinstance(ev, dict):
                continue
            params = ev.get("parameters", {})
            elem_id = ev.get("elementId") or ev.get("id", "?")
            area_val = pick(params, AREA_KEYS) or pick(ev, AREA_KEYS) or ev.get("area")
            name_val = (ev.get("name") or pick(params, NAME_KEYS) or pick(ev, NAME_KEYS)
                        or f"Floor {elem_id}")
            level_val = pick(params, LEVEL_KEYS) or pick(ev, LEVEL_KEYS) or ev.get("level")
            if area_val is not None:
                try:
                    area_float = extract_number(area_val)
                    if area_float > 0:
                        floor_details.append({"name": name_val, "area_sqft": area_float,
                                              "level": level_val, "element_id": elem_id})
                except ValueError:
                    pass
        if not floor_details:
            return {"audit_type": "floor_area_query", "status": "Unavailable",
                    "narrative": (f"Found {len(floor_ids)} floor element(s) but could not extract "
                                  "Area parameter values. The Area parameter may not be populated "
                                  "for these elements."),
                    "building_footprint_sqft": 0.0, "levels": []}

        level_groups: dict = defaultdict(list)
        for fd in floor_details:
            lv = fd.get("level") or "Unknown Level"
            if level_names and lv not in level_names:
                continue
            level_groups[lv].append(fd)  # fixed: audit_tools.py used defaultdict without import

        max_level_name, max_level_area, breakdown = "", 0.0, []
        for lv_name, elements in level_groups.items():
            lv_total = sum(e.get("area_sqft", 0) for e in elements)
            breakdown.append({"level_name": lv_name, "total_area_sqft": lv_total,
                              "element_count": len(elements),
                              "elements": elements if include_details else []})
            if lv_total > max_level_area:
                max_level_area, max_level_name = lv_total, lv_name
        if not breakdown:
            return {"audit_type": "floor_area_query", "status": "Unavailable",
                    "narrative": f"Floor elements found but none matched the requested "
                                 f"level filter: {level_names}",
                    "building_footprint_sqft": 0.0, "levels": []}

        total_all = sum(b["total_area_sqft"] for b in breakdown)
        parts = []
        if level_names:
            parts.insert(0, f"Filtered to level(s): {', '.join(level_names)}")
        parts.append(f"Floor area query complete. {len(floor_details)} floor element(s) "
                     f"across {len(breakdown)} level(s).")
        parts.append(f"Total floor area (all levels): {total_all:,.2f} sq ft")
        parts.append(f"Largest single-level area: {max_level_area:,.2f} sq ft ({max_level_name})")
        if include_details:
            parts.append("\nPer-Level Breakdown:")
            for b in breakdown:
                parts.append(f"  {b['level_name']}: {b['total_area_sqft']:,} sq ft "
                             f"({b['element_count']} element(s))")
                for e in b.get("elements", []):
                    parts.append(f"    - {e['name']}: {e['area_sqft']:,.2f} sq ft")

        return {"audit_type": "floor_area_query", "status": "Success",
                "total_floor_elements": len(floor_details),
                "total_area_all_levels_sqft": total_all,
                "building_footprint_sqft": max_level_area,
                "building_footprint_level": max_level_name,
                "levels": breakdown, "narrative": "\n".join(parts)}
    except UpstreamError as e:
        return {"audit_type": "floor_area_query", "error": str(e),
                "narrative": f"Error running floor area query: {e}"}


def run_lot_area_audit(up: Upstream, arguments: dict) -> dict:
    one_acre = 43560.0
    try:
        raw = up.call_tool("query_model", {
            "input": {"categories": ["OST_SiteProperty"], "searchScope": "AllViews",
                      "maxResults": 10}})
        element_ids = extract_element_ids(raw)
        if not element_ids:
            return {"audit_type": "lot_area", "status": "Unavailable",
                    "narrative": ("No OST_SiteProperty elements found in the model.\n"
                                  f"query_model raw: {get_raw_text(raw)[:300]!r}")}

        data_raw = up.call_tool("get_element_data", {
            "elementIds": [int(e) for e in element_ids],
            "outputOptions": {"basicElementInfo": True, "parametersOutputType": "AllParameters"}})
        raw_text_dump = get_raw_text(data_raw)
        elems = extract_elements(data_raw)

        AREA_KEYS_FULL = AREA_KEYS + ["GROSS_AREA", "FINISHED_AREA"]
        lots, params_debug = [], []
        for elem in elems:
            if not isinstance(elem, dict):
                continue
            eid = elem.get("elementId") or elem.get("id")
            params = elem.get("parameters", {})
            params_debug.append({"elem_keys": list(elem.keys())[:15],
                                 "param_keys": list(params.keys())[:20], "elem_id": eid})
            area_val = pick(params, AREA_KEYS_FULL) or pick(elem, AREA_KEYS_FULL)
            name_val = (elem.get("name") or pick(params, NAME_KEYS) or pick(elem, NAME_KEYS)
                        or f"Lot {eid}")
            if area_val is not None:
                try:
                    area_float = extract_number(area_val)
                    if area_float > 0:
                        lots.append({"name": name_val, "area_sqft": area_float, "element_id": eid})
                except ValueError:
                    pass

        # brute-force textual fallback (kept from the original)
        if not lots and raw_text_dump:
            bf = None
            for m in re.findall(r'(?:Area|area|AREA|"Area")\s*[=:]\s*"?([0-9,]+(?:\.[0-9]+))', raw_text_dump):
                try:
                    f = float(m.replace(",", ""))
                    if f > 0:
                        bf = f
                        break
                except ValueError:
                    continue
            if bf is None or bf <= 0:
                for v in re.findall(r'([0-9,]+(?:\.[0-9]+)?)\s*(?:sq\.?\s*ft|square\s*feet|SF)',
                                    raw_text_dump, re.IGNORECASE):
                    try:
                        f = float(v.replace(",", ""))
                        if f > 0:
                            bf = f
                            break
                    except ValueError:
                        continue
            if bf is not None and bf > 0:
                lots.append({"name": "Property Line", "area_sqft": bf, "element_id": element_ids[0]})

        if not lots:
            parts = [f"OST_SiteProperty IDs found: {element_ids}, but Area could not be read."]
            if params_debug:
                parts.append(f"Element structure: {json.dumps(params_debug, default=str)[:1200]}")
            return {"audit_type": "lot_area", "status": "Unavailable", "narrative": "\n".join(parts)}

        total_sqft = sum(l["area_sqft"] for l in lots)
        narrative = (f"Lot area audit complete. Found {len(lots)} property line(s).\n"
                     f"Total Area: {total_sqft:,.2f} sq ft ({total_sqft / one_acre:,.4f} acres)\n")
        for l in lots:
            narrative += f"  - {l['name']}: {l['area_sqft']:,.2f} sq ft\n"
        return {"audit_type": "lot_area", "status": "Success",
                "total_area_sqft": total_sqft, "total_area_acres": total_sqft / one_acre,
                "lots": lots, "narrative": narrative}
    except UpstreamError as e:
        return {"audit_type": "lot_area", "error": str(e),
                "narrative": f"Error running lot area audit: {e}"}


def run_lot_coverage_audit(up: Upstream, arguments: dict) -> dict:
    include_details = arguments.get("include_details", True)
    try:
        lot = run_lot_area_audit(up, arguments)
        if lot.get("status") == "Unavailable":
            return {"audit_type": "lot_coverage", "status": "Unavailable",
                    "narrative": "Lot coverage could not be calculated — lot area query failed.\n"
                                 + lot.get("narrative", "")}
        lot_sqft = lot.get("total_area_sqft", 0.0)
        if lot_sqft <= 0:
            return {"audit_type": "lot_coverage", "status": "Unavailable",
                    "narrative": "The lot area was calculated as zero — cannot compute coverage."}

        floor = run_floor_area_query(up, {"include_details": include_details})
        footprint = floor.get("building_footprint_sqft", 0.0)
        max_level = floor.get("building_footprint_level", "")
        breakdown = floor.get("levels", [])
        if footprint <= 0:
            return {"audit_type": "lot_coverage", "status": "Partial",
                    "lot_area_sqft": lot_sqft, "building_area_sqft": 0.0,
                    "building_coverage_percent": 0.0,
                    "narrative": ("Lot Coverage Audit — Partial Result.\n"
                                  f"Total Lot Area: {lot_sqft:,.2f} sq ft\n"
                                  "Building Footprint Area: 0.00 sq ft — no OST_Floors with "
                                  "populated Area parameters were found. Place rooms or "
                                  "verify floor elements have Area (or use axo_audit_floor_area "
                                  "for room-based area).\n"
                                  f"Detail: {floor.get('narrative', '')}")}

        pct = round((footprint / lot_sqft) * 100, 2)
        narrative = ("Lot Coverage Audit Complete.\n\n"
                     f"Total Lot Area: {lot_sqft:,.2f} sq ft\n"
                     f"Building Footprint Area: {footprint:,.2f} sq ft (largest single-level plate: {max_level})\n"
                     f"Building Lot Coverage: {pct:.2f}%\n")
        if include_details and breakdown:
            for b in breakdown:
                narrative += f"\n  {b.get('level_name', '?')}: {b.get('total_area_sqft', 0):,} sq ft"
        return {"audit_type": "lot_coverage", "status": "Success",
                "lot_area_sqft": lot_sqft, "building_area_sqft": footprint,
                "building_coverage_percent": pct, "max_level_name": max_level,
                "level_breakdown": breakdown, "narrative": narrative}
    except UpstreamError as e:
        return {"audit_type": "lot_coverage", "error": str(e),
                "narrative": f"Error running lot coverage audit: {e}"}


def run_septic_audit(up: Upstream, arguments: dict) -> dict:
    """Septic settlement audit (counts fixtures/property lines with required 50 ft)."""
    jurisdiction = arguments.get("jurisdiction", "default")

    def _counts(tool_input):
        try:
            r = up.call_tool("query_model", {"input": tool_input})
        except UpstreamError:
            return 0
        return len(extract_element_ids(r))

    try:
        tanks = _counts({"categories": ["OST_PlumbingFixtures"], "searchScope": "AllViews",
                         "maxResults": 200})
        lines = _counts({"categories": ["OST_PropertyLine"], "searchScope": "AllViews",
                         "maxResults": 200})
    except Exception as exc:
        return {"error": f"Failed to query Revit model: {exc}"}
    required_ft = 50.0
    return {"audit_type": "septic", "jurisdiction": jurisdiction,
            "results": {"tanks_found": tanks, "lines_found": lines},
            "narrative": (f"Septic audit: found {tanks} plumbing fixture(s) and {lines} "
                          f"property line(s). Required clearance: {required_ft} ft. "
                          "Distance geometry is not exposed by the current add-in — counts "
                          "only; verify setbacks manually on the plan.")}


def run_energy_audit(up: Upstream, arguments: dict) -> dict:
    return {"audit_type": "energy",
            "jurisdiction": arguments.get("jurisdiction", "default"),
            "narrative": ("Energy envelope audit (U-factor/SHGC extraction) is a placeholder "
                          "in the original Axoworks engine as well. Use axo_audit_wwr for "
                          "glass fraction, and get_element_data with AllParameters on "
                          "windows/walls for U-values where the model carries them.")}


def run_wwr_audit(up: Upstream, arguments: dict) -> dict:
    max_wwr = arguments.get("max_wwr_percent", 40.0)
    try:
        win = up.call_tool("query_model", {
            "input": {"categories": ["OST_Windows"], "searchScope": "AllViews", "maxResults": 500}})
        wall = up.call_tool("query_model", {
            "input": {"categories": ["OST_Walls"], "searchScope": "AllViews", "maxResults": 500}})
        win_ids = extract_element_ids(win)
        wall_ids = extract_element_ids(wall)
    except UpstreamError as e:
        return {"audit_type": "wwr", "max_wwr_percent": max_wwr, "error": str(e)}
    return {"audit_type": "wwr", "max_wwr_percent": max_wwr,
            "results": {"windows_found": len(win_ids), "walls_found": len(wall_ids)},
            "narrative": (f"WWR audit: {len(win_ids)} window(s) and {len(wall_ids)} wall(s) "
                          f"against a {max_wwr}% limit. WWR requires glazing/wall *areas*, "
                          "which the read-only add-in does not expose directly; use "
                          "get_element_data(KeyParameters) on both sets and compute "
                          "glazed/wall area, or the door/window schedule CSV for "
                          "WIDTH×HEIGHT rows. Deterministic math pending add-in geometry.")}


def run_setback_audit(up: Upstream, arguments: dict) -> dict:
    return {"audit_type": "setback", "status": "unavailable",
            "narrative": ("The Setback Audit is unavailable in the original Axoworks engine "
                          "as well: the Autodesk Revit MCP Server (read-only preview) does not "
                          "export property-line geometry. Check back in future add-in "
                          "updates — or use Revit's own 'Property Line Proximity Analysis' "
                          "on the plan.")}


def axo_tools() -> list:
    return [
        {"name": "axo_audit_floor_area",
         "description": ("Query floor area data from the active Revit model. Returns total "
                         "floor area and per-room breakdown, grouped by level. Optionally "
                         "filter by one or more level names (e.g. FP1.GARAGE, FP2.ADU)."),
         "inputSchema": {"type": "object", "properties": {
             "level_names": {"type": "array", "items": {"type": "string"},
                             "description": "Optional level name filter (e.g. ['FP1.GARAGE'])."},
             "include_room_details": {"type": "boolean", "default": True}}},
         "annotations": {"readOnlyHint": True}},
        {"name": "axo_query_floor_area",
         "description": ("Query floor element areas (OST_Floors, Area parameter), grouped by "
                         "Level; returns the largest single-level floor plate as building "
                         "footprint. Use this to determine the building footprint for lot "
                         "coverage calculations."),
         "inputSchema": {"type": "object", "properties": {
             "level_names": {"type": "array", "items": {"type": "string"}},
             "include_details": {"type": "boolean", "default": True}}},
         "annotations": {"readOnlyHint": True}},
        {"name": "axo_audit_lot_area",
         "description": ("Calculate the lot area (area enclosed by property lines) from the "
                         "active Revit model. Reads OST_SiteProperty Area parameters; returns "
                         "sq ft and acres."),
         "inputSchema": {"type": "object", "properties": {
             "area_unit": {"type": "string", "default": "both",
                           "enum": ["sqft", "acres", "both"]}}},
         "annotations": {"readOnlyHint": True}},
        {"name": "axo_audit_lot_coverage",
         "description": ("Lot coverage percent = building footprint (largest single-level "
                         "floor plate) / lot area × 100. Composed from axo_audit_lot_area "
                         "+ axo_query_floor_area."),
         "inputSchema": {"type": "object", "properties": {
             "area_unit": {"type": "string", "default": "both", "enum": ["sqft", "acres", "both"]},
             "include_details": {"type": "boolean", "default": True}}},
         "annotations": {"readOnlyHint": True}},
        {"name": "axo_audit_septic",
         "description": "Septic clearance audit: counts plumbing fixtures and property "
                        "lines against the standard 50 ft clearance (geometry pending "
                        "add-in updates).",
         "inputSchema": {"type": "object", "properties": {
             "jurisdiction": {"type": "string", "default": "default"}}},
         "annotations": {"readOnlyHint": True}},
        {"name": "axo_audit_energy",
         "description": "Energy envelope audit (placeholder parity with the original "
                        "engine; see narrative).",
         "inputSchema": {"type": "object", "properties": {
             "jurisdiction": {"type": "string", "default": "default"}}},
         "annotations": {"readOnlyHint": True}},
        {"name": "axo_audit_wwr",
         "description": "Window-to-Wall Ratio audit: counts windows/walls against the "
                        "limit; full area-ratio math pending add-in geometry (see "
                        "narrative).",
         "inputSchema": {"type": "object", "properties": {
             "max_wwr_percent": {"type": "number", "default": 40.0}}},
         "annotations": {"readOnlyHint": True}},
        {"name": "axo_audit_setback",
         "description": "Setback distance audit (unavailable in the original engine too — "
                        "property-line geometry is not exported by the add-in; see narrative).",
         "inputSchema": {"type": "object", "properties": {
             "output_unit": {"type": "string", "default": "ft_in",
                             "enum": ["ft_in", "ft", "in"]}}},
         "annotations": {"readOnlyHint": True}},
    ]


HANDLERS = {
    "axo_audit_floor_area": run_floor_area_audit,
    "axo_query_floor_area": run_floor_area_query,
    "axo_audit_lot_area": run_lot_area_audit,
    "axo_audit_lot_coverage": run_lot_coverage_audit,
    "axo_audit_septic": run_septic_audit,
    "axo_audit_energy": run_energy_audit,
    "axo_audit_wwr": run_wwr_audit,
    "axo_audit_setback": run_setback_audit,
}


# ===========================================================================
# MCP stdio server loop (client: DSH via dsh-mcp-client)
# ===========================================================================

def respond(rid: Any, payload: dict) -> None:
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


def main() -> int:
    exe = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_EXE
    up = Upstream(exe)
    axo = axo_tools()

    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        rid = None
        try:
            msg = json.loads(raw)
            rid = msg.get("id")
            method = msg.get("method")
            params = msg.get("params") or {}
        except json.JSONDecodeError as e:
            respond(rid, {"jsonrpc": "2.0", "id": rid,
                          "error": {"code": -32700, "message": f"parse error: {e}"}})
            continue

        try:
            if method == "initialize":
                up.ensure()
                respond(rid, {"jsonrpc": "2.0", "id": rid, "result": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION}}})
            elif method == "notifications/initialized":
                try:
                    up.discover_instance()  # warm the attach once, cheap thereafter
                except UpstreamError as e:
                    log.warning("warm attach failed (will retry lazily): %s", e)
            elif method == "ping":
                respond(rid, {"jsonrpc": "2.0", "id": rid, "result": {}})
            elif method == "tools/list":
                respond(rid, {"jsonrpc": "2.0", "id": rid,
                              "result": {"tools": up.list_tools() + axo}})
            elif method == "tools/call":
                name = params.get("name")
                arguments = params.get("arguments") or {}
                if name in HANDLERS:
                    result = HANDLERS[name](up, arguments)
                    envelope = {"content": [{"type": "text",
                                             "text": json.dumps(result, indent=2, default=str)}]}
                    if isinstance(result, dict) and "error" in result:
                        envelope["isError"] = True
                    respond(rid, {"jsonrpc": "2.0", "id": rid, "result": envelope})
                elif name:
                    result = up.call_tool(name, arguments)
                    respond(rid, {"jsonrpc": "2.0", "id": rid, "result": result})
                else:
                    respond(rid, {"jsonrpc": "2.0", "id": rid,
                                  "error": {"code": -32602, "message": "missing tool name"}})
            elif method in ("resources/list", "prompts/list"):
                respond(rid, {"jsonrpc": "2.0", "id": rid,
                              "result": {("resources" if "resources" in method else "prompts"): []}})
            else:
                respond(rid, {"jsonrpc": "2.0", "id": rid,
                              "error": {"code": -32601, "message": f"method not found: {method}"}})
        except UpstreamError as e:
            respond(rid, {"jsonrpc": "2.0", "id": rid,
                          "error": {"code": -32000, "message": str(e)}})
        except Exception as e:  # never kill the loop on a bad request
            log.exception("unhandled error")
            respond(rid, {"jsonrpc": "2.0", "id": rid,
                          "error": {"code": -32603, "message": str(e)}})
    return 0


if __name__ == "__main__":
    sys.exit(main())
