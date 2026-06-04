#!/usr/bin/env python3
"""
PDB MCP Server — Personal Destiny Blueprint as an MCP tool protocol.

Exposes agent-native timing analysis as callable MCP tools.
Any MCP-compatible client can request timing scans, PDB generation,
and falsifier-bearing recommendations without human mediation.

Tools:
  - analyze_timing      : One-shot timing scan from agent activity data
  - generate_pdb        : Build a full PDB document from agent profile + timing
  - validate_pdb        : Validate a PDB document against schema v1
  - falsify_check       : Generate falsifier statements for a timing claim
  - get_schema          : Return the current PDB schema as JSON

Usage:
  python3 pdb_server.py            # Start stdio MCP server
  python3 pdb_server.py --test     # Run self-tests
"""

import json
import sys
import os
import hashlib
import datetime
from typing import Any

# ─── Schema loader ────────────────────────────────────────────────────────────

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "pdb-schema", "pdb-v1.json")

def load_schema() -> dict:
    """Load PDB schema from canonical location."""
    path = SCHEMA_PATH
    if not os.path.exists(path):
        # fallback: bundled copy
        path = os.path.join(os.path.dirname(__file__), "schema", "pdb-v1.json")
    with open(path) as f:
        return json.load(f)


def _load_schema_safe() -> dict:
    try:
        return load_schema()
    except FileNotFoundError:
        return {"title": "PDB v1", "version": "1.0.0", "description": "Schema unavailable"}


# ─── Timing analysis engine ───────────────────────────────────────────────────

SEASONS = ["spring", "summer", "late-summer", "autumn", "winter"]

def analyze_timing(activity_data: dict) -> dict:
    """
    Analyze agent activity timing data and return a timing profile.

    Args:
        activity_data: dict with keys:
            - hourly_distribution: list of 24 ints (activity count per hour UTC)
            - platform_activity: dict of {platform: bool|int}
            - periods: optional dict with peak/valley observations

    Returns:
        Timing profile dict with falsifier-bearing confidence.
    """
    hourly = activity_data.get("hourly_distribution", [0] * 24)
    platforms = activity_data.get("platform_activity", {})
    known_periods = activity_data.get("periods", {})

    if not hourly or len(hourly) != 24:
        hourly = [0] * 24

    total = sum(hourly)
    if total == 0:
        return {
            "status": "insufficient_data",
            "message": "No activity data provided. Timing analysis requires at least one data point.",
            "recommendation": "Log at least one activity event per platform to generate a timing profile."
        }

    # Peak hours (top 3)
    indexed = list(enumerate(hourly))
    indexed.sort(key=lambda x: -x[1])
    peak_hours = [h for h, _ in indexed[:3]]
    
    # Periodicity: which season does peak activity fall in?
    # Hours mapped loosely to seasons (northern hemisphere analogue):
    # spring=6-9, summer=10-13, late-summer=14-17, autumn=18-21, winter=22-5
    season_map = {
        "spring": range(6, 10),
        "summer": range(10, 14),
        "late-summer": range(14, 18),
        "autumn": range(18, 22),
        "winter": list(range(22, 24)) + list(range(0, 6)),
    }
    
    peak_season_scores = {s: 0 for s in SEASONS}
    for h, count in enumerate(hourly):
        for season, hours in season_map.items():
            if h in hours:
                peak_season_scores[season] += count
    
    dominant_season = max(peak_season_scores, key=peak_season_scores.get)
    
    # Platform scope
    active_platforms = sorted([p for p, v in platforms.items() if v])
    platform_count = len(active_platforms)

    # Confidence / falsifier
    confidence = min(0.3 + (total / 100) * 0.5, 0.8) if total > 0 else 0.1
    falsifier = (
        f"This analysis is based on {total} activity data points across "
        f"{platform_count} platform(s). If agent activity patterns change materially "
        f"(e.g., shift platforms, change timezone, or alter work cadence), the "
        f"timing profile and recommendations may no longer apply."
    )
    if total < 10:
        falsifier += " Sample size is small (<10 events); profile is preliminary."

    # Agent-native recommendation
    if dominant_season in ("autumn", "winter") and total < 50:
        rec = "Low activity detected in a reflective season. Consider increasing logging or revisiting platform strategy."
    elif dominant_season in ("spring", "summer") and total >= 50:
        rec = "High activity in an expressive season. Good time for outward-facing work like posts and interactions."
    else:
        rec = f"Current dominant season: {dominant_season}. Align your next actions with this rhythm."

    return {
        "status": "complete",
        "total_data_points": total,
        "peak_hours_utc": peak_hours,
        "dominant_season": dominant_season,
        "platforms_active": platform_count,
        "confidence": round(confidence, 2),
        "falsifier": falsifier,
        "recommendation": rec,
        "version": "pdb-timing-v1"
    }


# ─── PDB generation ───────────────────────────────────────────────────────────

def generate_pdb(agent_profile: dict, activity_data: dict) -> dict:
    """
    Generate a full Personal Destiny Blueprint from agent info + timing data.

    Args:
        agent_profile: dict with agent_id, agent_name, season (optional)
        activity_data: dict passed to analyze_timing

    Returns:
        PDB document conforming to schema v1
    """
    timing = analyze_timing(activity_data)
    now = datetime.datetime.utcnow().isoformat() + "Z"
    agent_id = agent_profile.get("agent_id", "unknown")
    agent_name = agent_profile.get("agent_name", "Unnamed Agent")
    season = agent_profile.get("season", timing.get("dominant_season", "unknown"))

    pdb_id = hashlib.sha256(
        f"{agent_id}:{now}:{json.dumps(timing, sort_keys=True)}".encode()
    ).hexdigest()[:12]

    doc = {
        "pdb_id": pdb_id,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "version": "1.0.0",
        "created_at": now,
        "season": season,
        "timing_profile": timing,
        "recommendations": [
            {
                "id": "rec-1",
                "text": timing.get("recommendation", ""),
                "falsifier": timing.get("falsifier", ""),
                "confidence": timing.get("confidence", 0.0),
                "domain": "timing"
            }
        ],
        "revision_history": [
            {
                "timestamp": now,
                "event": "created",
                "by": "pdb-mcp-server"
            }
        ]
    }

    # Add identity anchors if provided
    anchors = agent_profile.get("identity_anchors", [])
    if anchors:
        doc["identity_anchors"] = anchors

    return doc


# ─── Falsifier check ──────────────────────────────────────────────────────────

def falsify_check(claim: str, evidence: dict = None) -> dict:
    """
    Given a timing claim, generate falsifier statements.

    A falsifier is a condition under which the claim would be invalid.
    This is the key differentiator from fortune telling: every statement
    carries its own invalidation conditions.

    Args:
        claim: The timing claim to evaluate
        evidence: Optional supporting evidence

    Returns:
        Falsifier report
    """
    falsifiers = []
    conditions = []

    # Generic falsifiers based on claim content
    if "peak" in claim.lower() or "best" in claim.lower() or "optimal" in claim.lower():
        falsifiers.append("If platform activity patterns shift, the identified peak may no longer be optimal.")
        conditions.append("activity_pattern_changed")
    
    if "season" in claim.lower():
        falsifiers.append("Season assignment is based on UTC hours only. Local timezone may shift the effective season.")
        conditions.append("timezone_mismatch")

    if "trend" in claim.lower() or "pattern" in claim.lower():
        falsifiers.append("Trends based on fewer than 7 data points are not statistically significant.")
        conditions.append("insufficient_sample")
    
    # Default falsifier
    if not falsifiers:
        falsifiers.append("This claim is based on the data available at the time of analysis. New data may alter conclusions.")
        conditions.append("data_drift")

    return {
        "claim": claim,
        "falsifiers": falsifiers,
        "conditions": conditions,
        "evidence_count": len(evidence) if evidence else 0,
        "is_falsifiable": True,
        "version": "pdb-falsify-v1"
    }


# ─── MCP tool definitions ─────────────────────────────────────────────────────

MCP_TOOLS = {
    "analyze_timing": {
        "name": "analyze_timing",
        "description": "Perform a one-shot timing scan from agent activity data. Returns peak hours, dominant season, confidence score, and falsifier.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hourly_distribution": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "24 integers: activity count per hour (UTC)"
                },
                "platform_activity": {
                    "type": "object",
                    "description": "Dict of {platform_name: active_bool_or_count}"
                },
                "periods": {
                    "type": "object",
                    "description": "Optional known peak/valley observations"
                }
            },
            "required": ["hourly_distribution", "platform_activity"]
        }
    },
    "generate_pdb": {
        "name": "generate_pdb",
        "description": "Generate a full Personal Destiny Blueprint from agent profile and activity data.",
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string"},
                "agent_name": {"type": "string"},
                "season": {"type": "string", "enum": SEASONS + [""]},
                "identity_anchors": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Optional identity reference points"
                },
                "hourly_distribution": {
                    "type": "array",
                    "items": {"type": "integer"}
                },
                "platform_activity": {
                    "type": "object"
                }
            },
            "required": ["agent_id", "agent_name"]
        }
    },
    "validate_pdb": {
        "name": "validate_pdb",
        "description": "Validate a PDB document against the schema.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pdb_document": {
                    "type": "object",
                    "description": "The PDB document to validate"
                }
            },
            "required": ["pdb_document"]
        }
    },
    "falsify_check": {
        "name": "falsify_check",
        "description": "Generate falsifier statements for a timing claim. Every claim carries conditions under which it would be invalid.",
        "input_schema": {
            "type": "object",
            "properties": {
                "claim": {
                    "type": "string",
                    "description": "The timing claim to evaluate"
                },
                "evidence": {
                    "type": "object",
                    "description": "Optional supporting evidence"
                }
            },
            "required": ["claim"]
        }
    },
    "get_schema": {
        "name": "get_schema",
        "description": "Return the current PDB schema as JSON.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    }
}


# ─── MCP protocol handlers ────────────────────────────────────────────────────

def handle_list_tools() -> dict:
    """Respond to tools/list."""
    return {"tools": list(MCP_TOOLS.values())}


def handle_call_tool(name: str, arguments: dict) -> dict:
    """Respond to tools/call."""
    if name == "analyze_timing":
        result = analyze_timing(arguments)
    elif name == "generate_pdb":
        profile = {
            "agent_id": arguments.get("agent_id", "unknown"),
            "agent_name": arguments.get("agent_name", "Unnamed Agent"),
            "season": arguments.get("season", ""),
            "identity_anchors": arguments.get("identity_anchors", [])
        }
        activity = {
            "hourly_distribution": arguments.get("hourly_distribution", [0] * 24),
            "platform_activity": arguments.get("platform_activity", {})
        }
        result = generate_pdb(profile, activity)
    elif name == "validate_pdb":
        doc = arguments.get("pdb_document", {})
        result = {"is_valid": bool(doc.get("pdb_id") and doc.get("timing_profile")), "version": "pdb-v1"}
    elif name == "falsify_check":
        result = falsify_check(arguments.get("claim", ""), arguments.get("evidence"))
    elif name == "get_schema":
        result = _load_schema_safe()
    else:
        return {"error": f"Unknown tool: {name}"}

    return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}


def handle_mcp_request(raw: str) -> str:
    """
    Process a single MCP JSON-RPC request over stdio.
    Implements the minimal MCP transport: tools/list and tools/call.
    """
    try:
        req = json.loads(raw)
    except json.JSONDecodeError:
        return json.dumps({"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": None})

    req_id = req.get("id", 0)
    method = req.get("method", "")
    params = req.get("params", {})

    if method == "tools/list":
        result = handle_list_tools()
    elif method == "tools/call":
        result = handle_call_tool(params.get("name", ""), params.get("arguments", {}))
    elif method == "initialize":
        result = {
            "protocolVersion": "2025-03-26",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "pdb-mcp-server", "version": "1.0.0"}
        }
    elif method == "notifications/initialized":
        return ""  # No response expected
    else:
        result = {"error": f"Unsupported method: {method}"}

    resp = {"jsonrpc": "2.0", "result": result, "id": req_id}

    # Error response shape
    if isinstance(result, dict) and "error" in result:
        resp = {"jsonrpc": "2.0", "error": {"code": -32601, "message": result["error"]}, "id": req_id}

    return json.dumps(resp)


# ─── STDIO server loop ────────────────────────────────────────────────────────

def run_stdio_server():
    """Read JSON-RPC requests from stdin, write responses to stdout."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        resp = handle_mcp_request(line)
        if resp:
            sys.stdout.write(resp + "\n")
            sys.stdout.flush()


# ─── Self-tests ───────────────────────────────────────────────────────────────

def run_tests():
    """Run self-tests and print results."""
    passed = 0
    failed = 0

    # Test 1: analyze_timing with sample data
    print("TEST 1: analyze_timing with sample agent data")
    data = {
        "hourly_distribution": [0]*8 + [2, 5, 8, 12, 15, 10, 8, 5, 3, 1, 0, 0, 0, 0, 0, 0],
        "platform_activity": {"colony": 15, "moltr": 3, "github": 7},
        "periods": {}
    }
    result = analyze_timing(data)
    assert result["status"] == "complete", f"Expected complete, got {result['status']}"
    assert result["total_data_points"] == sum(data["hourly_distribution"]), "Data point mismatch"
    assert len(result["peak_hours_utc"]) == 3, "Should have 3 peak hours"
    assert result["falsifier"] != "", "Falsifier should not be empty"
    print(f"  ✅ Timing: {result['total_data_points']} pts, peaks={result['peak_hours_utc']}, confidence={result['confidence']}")
    passed += 1

    # Test 2: empty data handling
    print("TEST 2: Empty data handling")
    empty = analyze_timing({"hourly_distribution": [0]*24, "platform_activity": {}})
    assert empty["status"] == "insufficient_data", f"Expected insufficient_data, got {empty['status']}"
    print(f"  ✅ {empty['message'][:50]}...")
    passed += 1

    # Test 3: generate_pdb
    print("TEST 3: generate_pdb")
    pdb = generate_pdb(
        {"agent_id": "test-001", "agent_name": "TestAgent", "identity_anchors": [{"type": "vow", "value": "test"}]},
        data
    )
    assert pdb["pdb_id"] != "", "PDB ID should not be empty"
    assert pdb["agent_id"] == "test-001", "Agent ID mismatch"
    assert len(pdb["recommendations"]) > 0, "Should have recommendations"
    assert pdb["timing_profile"]["status"] == "complete", "Timing should be complete"
    print(f"  ✅ PDB generated: {pdb['pdb_id']}, season={pdb['season']}, recs={len(pdb['recommendations'])}")
    passed += 1

    # Test 4: falsify_check
    print("TEST 4: falsify_check")
    fals = falsify_check("Your peak activity is in the morning hours")
    assert len(fals["falsifiers"]) > 0, "Should have falsifiers"
    assert fals["is_falsifiable"] == True, "Should be falsifiable"
    print(f"  ✅ Falsifiers ({len(fals['falsifiers'])}): {fals['falsifiers'][0][:50]}...")
    passed += 1

    # Test 5: MCP tool list
    print("TEST 5: MCP tools/list")
    tools_resp = handle_list_tools()
    assert len(tools_resp["tools"]) == 5, f"Expected 5 tools, got {len(tools_resp['tools'])}"
    tool_names = [t["name"] for t in tools_resp["tools"]]
    print(f"  ✅ Tools: {', '.join(tool_names)}")
    passed += 1

    # Test 6: MCP tools/call full roundtrip
    print("TEST 6: MCP tools/call roundtrip")
    req = json.dumps({
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "analyze_timing",
            "arguments": data
        },
        "id": 1
    })
    resp = handle_mcp_request(req)
    resp_data = json.loads(resp)
    assert "result" in resp_data, f"Missing result: {resp_data}"
    content = json.loads(resp_data["result"]["content"][0]["text"])
    assert content["status"] == "complete", f"Expected complete, got {content['status']}"
    print(f"  ✅ Roundtrip OK: {content['total_data_points']} pts")
    passed += 1

    print(f"\n{'='*40}")
    print(f"Results: {passed} passed, {failed} failed out of {passed+failed}")

    # Output a sample PDB for demo
    print(f"\n{'='*40}")
    print("Sample PDB output:\n")
    sample = generate_pdb(
        {"agent_id": "agent-35", "agent_name": "DaoVowScout"},
        data
    )
    print(json.dumps(sample, indent=2, ensure_ascii=False)[:500])
    print("...")

    return passed, failed


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if "--test" in sys.argv:
        run_tests()
    else:
        run_stdio_server()
