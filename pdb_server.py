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
import random
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
        return {"title": "PDB v1", "version": "1.1.0", "description": "Schema unavailable"}


# ─── Timing analysis engine ───────────────────────────────────────────────────

SEASONS = ["spring", "summer", "late-summer", "autumn", "winter"]
# ─── Scoreboard: published invalidation tracking ──────────────────────────
# Agents can query this to see if PDB falsifiers actually fire.
# Tautology counter: if no PDB ever gets invalidated by its own falsifier,
# the falsifiers are decorative.
PDB_SCOREBOARD = {
    "_meta": {
        "version": "1.1.0",
        "created": __import__("datetime").datetime.utcnow().isoformat() + "Z"
    },
    "summary": {
        "total_pdbs": 0,
        "invalidated_by_falsifier": 0,
        "pending_evaluation": 0,
        "fire_rate": 0.0
    },
    "records": []
}


def update_scoreboard(pdb_id: str, agent_id: str, preregistered: list = None):
    """Record a new PDB on the scoreboard."""
    now = __import__("datetime").datetime.utcnow().isoformat() + "Z"
    record = {
        "pdb_id": pdb_id,
        "agent_id": agent_id,
        "created_at": now,
        "preregistered_falsifiers": preregistered or [],
        "invalidated": False,
        "invalidated_at": None
    }
    PDB_SCOREBOARD["records"].append(record)
    PDB_SCOREBOARD["summary"]["total_pdbs"] = len(PDB_SCOREBOARD["records"])
    PDB_SCOREBOARD["summary"]["pending_evaluation"] = sum(
        1 for r in PDB_SCOREBOARD["records"] if not r["invalidated"]
    )
    return record


def invalidate_pdb(pdb_id: str) -> dict:
    """Mark a PDB as invalidated by its own falsifier."""
    now = __import__("datetime").datetime.utcnow().isoformat() + "Z"
    for r in PDB_SCOREBOARD["records"]:
        if r["pdb_id"] == pdb_id and not r["invalidated"]:
            r["invalidated"] = True
            r["invalidated_at"] = now
            break
    s = PDB_SCOREBOARD["summary"]
    s["invalidated_by_falsifier"] = sum(1 for r in PDB_SCOREBOARD["records"] if r["invalidated"])
    s["pending_evaluation"] = sum(1 for r in PDB_SCOREBOARD["records"] if not r["invalidated"])
    s["fire_rate"] = round(s["invalidated_by_falsifier"] / max(1, s["total_pdbs"]), 4)
    return PDB_SCOREBOARD["summary"]


def get_scoreboard() -> dict:
    """Return current scoreboard."""
    s = PDB_SCOREBOARD["summary"]
    s["invalidated_by_falsifier"] = sum(1 for r in PDB_SCOREBOARD["records"] if r["invalidated"])
    s["pending_evaluation"] = sum(1 for r in PDB_SCOREBOARD["records"] if not r["invalidated"])
    s["fire_rate"] = round(s["invalidated_by_falsifier"] / max(1, s["total_pdbs"]), 4)
    return PDB_SCOREBOARD




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

    # Control baselines (v1.1): compare against randomized windows
    # The falsifier is only load-bearing if the selected window beats a control
    random.seed(total)  # Deterministic shuffle based on data
    all_hours = list(enumerate(hourly))
    random.shuffle(all_hours)
    random_peak = [h for h, _ in all_hours[:3]]
    control_diff = abs(sum(peak_hours) - sum(random_peak)) / max(3, sum(peak_hours))
    
    control_baseline = {
        "random_window_peaks": sorted(random_peak),
        "delta_vs_random": round(control_diff, 3),
        "shuffled_element_peaks": sorted(hourly[:3] if len(hourly) >= 3 else []),
        "note": "If delta_vs_random < 0.1, the peak detection is indistinguishable from noise."
    }

    return {
        "status": "complete",
        "total_data_points": total,
        "peak_hours_utc": peak_hours,
        "dominant_season": dominant_season,
        "platforms_active": platform_count,
        "confidence": round(confidence, 2),
        "falsifier": falsifier,
        "falsifier_type": "self_evaluable",
        "control_baseline": control_baseline,
        "recommendation": rec,
        "version": "pdb-timing-v1.1"
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

    # Pre-register falsifiers from the timing profile
    preregistered_list = [
        preregister_falsifier(
            claim=timing.get("recommendation", "Timing analysis"),
            falsifier=timing.get("falsifier", ""),
            window={"interval": "next_500_tool_calls", "cadence": "batch",
                    "start_time": now},
            witness="self"
        )
    ]
    
    # Record on scoreboard
    update_scoreboard(pdb_id, agent_id, preregistered_list)
    
    # Published scoreboard info for this server
    scoreboard_summary = get_scoreboard()["summary"]

    doc = {
        "pdb_id": pdb_id,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "version": "1.1.0",
        "created_at": now,
        "season": season,
        "timing_profile": timing,
        "preregistered_falsifiers": preregistered_list,
        "scoreboard_info": {
            "total_pdbs_this_server": scoreboard_summary["total_pdbs"],
            "invalidation_rate_this_server": scoreboard_summary["fire_rate"]
        },
        "recommendations": [
            {
                "id": "rec-1",
                "text": timing.get("recommendation", ""),
                "falsifier": timing.get("falsifier", ""),
                "falsifier_type": "self_evaluable",
                "confidence": timing.get("confidence", 0.0),
                "domain": "timing",
                "preregistered": True
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
    
    return doc

def preregister_falsifier(claim: str, falsifier: str, window: dict, witness: str = "self") -> dict:
    """
    Pre-register a falsifier with a fixed window before evaluation data exists.
    A falsifier that is defined BEFORE the observation period is falsifiable;
    one defined after the fact is just a description.

    Args:
        claim: The claim being made
        falsifier: The condition under which the claim would be invalid
        window: Dict with 'interval' (e.g. "next_500_tool_calls" or "next_7_days"),
                'cadence' (how often to check), and 'start_time' (ISO string)
        witness: Who evaluates the falsifier — "self" (agent checks own logs),
                 "exogenous" (third-party observer required),
                 "marketplace" (marketplace dispute resolver)

    Returns:
        Pre-registered falsifier record with timestamp
    """
    now = __import__("datetime").datetime.utcnow().isoformat() + "Z"
    
    falsifier_type = "self_evaluable" if witness == "self" else "requires_exogenous_witness"
    
    record = {
        "id": hashlib.sha256(f"{claim}:{now}:{falsifier}".encode()).hexdigest()[:12],
        "claim": claim,
        "falsifier": falsifier,
        "falsifier_type": falsifier_type,
        "evaluator": witness,
        "window": {
            "interval": window.get("interval", "unbounded"),
            "cadence": window.get("cadence", "once"),
            "start_time": window.get("start_time", now),
            "preregistered_at": now
        },
        "status": "pending",
        "evaluation_result": None,
        "evaluated_at": None
    }
    
    return record


def falsify_check(claim: str, evidence: dict = None, preregistered: list = None) -> dict:
    """
    Given a timing claim, generate falsifier statements with metadata tags.

    A falsifier is a condition under which the claim would be invalid.
    This is the key differentiator from fortune telling: every statement
    carries its own invalidation conditions.

    v1.1.0 addition: Every falsifier now carries a 'falsifier_type' tag
    ('self_evaluable' or 'requires_exogenous_witness') so consumers know
    at parse time whether a claim is third-party-checkable or decorative.

    Args:
        claim: The timing claim to evaluate
        evidence: Optional supporting evidence (dict or None)
        preregistered: Optional list of preregistered falsifier records

    Returns:
        Falsifier report with tagged falsifiers
    """
    falsifier_items = []
    
    # Process preregistered falsifiers first (they have priority)
    if preregistered:
        for pf in preregistered:
            falsifier_items.append({
                "falsifier": pf.get("falsifier", ""),
                "falsifier_type": pf.get("falsifier_type", "self_evaluable"),
                "evaluator": pf.get("evaluator", "self"),
                "window": pf.get("window", {}),
                "preregistered": True,
                "id": pf.get("id", "")
            })
    
    # Generate falsifiers based on claim content
    claim_lower = claim.lower()
    
    peak_detected = any(w in claim_lower for w in ["peak", "best", "optimal", "high"])
    season_detected = any(s in claim_lower for s in ["spring", "summer", "autumn", "winter", "season"])
    trend_detected = any(w in claim_lower for w in ["trend", "pattern", "shift", "change"])
    
    needs_default = True
    
    if peak_detected:
        falsifier_items.append({
            "falsifier": "If platform activity patterns shift, the identified peak may no longer be optimal.",
            "falsifier_type": "requires_exogenous_witness",
            "evaluator": "third_party_tracker",
            "window": {"interval": "next_500_tool_calls", "cadence": "batch", "start_time": None},
            "preregistered": False,
            "id": ""
        })
        needs_default = False
    
    if season_detected:
        falsifier_items.append({
            "falsifier": "Season assignment is based on UTC hours only. Local timezone may shift the effective season.",
            "falsifier_type": "self_evaluable",
            "evaluator": "agent",
            "window": {"interval": "next_evaluation", "cadence": "once", "start_time": None},
            "preregistered": False,
            "id": ""
        })
        needs_default = False
    
    if trend_detected:
        falsifier_items.append({
            "falsifier": "Trends based on fewer than 7 data points are not statistically significant.",
            "falsifier_type": "self_evaluable",
            "evaluator": "agent",
            "window": {"interval": "ongoing", "cadence": "continuous", "start_time": None},
            "preregistered": False,
            "id": ""
        })
        needs_default = False
    
    if needs_default:
        falsifier_items.append({
            "falsifier": "This claim is based on the data available at the time of analysis. New data may alter conclusions.",
            "falsifier_type": "self_evaluable",
            "evaluator": "agent",
            "window": {"interval": "until_next_pdb", "cadence": "once", "start_time": None},
            "preregistered": False,
            "id": ""
        })
    
    return {
        "claim": claim,
        "falsifiers": falsifier_items,
        "falsifier_count": len(falsifier_items),
        "self_evaluable_count": sum(1 for f in falsifier_items if f["falsifier_type"] == "self_evaluable"),
        "requires_exogenous_count": sum(1 for f in falsifier_items if f["falsifier_type"] == "requires_exogenous_witness"),
        "evidence_count": len(evidence) if evidence else 0,
        "is_falsifiable": any(f["preregistered"] for f in falsifier_items) or len(falsifier_items) > 0,
        "version": "pdb-falsify-v1.1",
        "note": "A falsifier is only load-bearing if it carries 'preregistered: True'. Generate one via preregister_falsifier()."
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
    "preregister_falsifier": {
        "name": "preregister_falsifier",
        "description": "Pre-register a falsifier with a fixed window before evaluation data exists. A falsifier defined BEFORE observation is falsifiable; one defined after is just description.",
        "input_schema": {
            "type": "object",
            "properties": {
                "claim": {"type": "string"},
                "falsifier": {"type": "string", "description": "Condition under which the claim would be invalid"},
                "window": {
                    "type": "object",
                    "properties": {
                        "interval": {"type": "string", "description": "e.g. next_500_tool_calls, next_7_days"},
                        "cadence": {"type": "string", "description": "How often to check"}
                    }
                },
                "witness": {"type": "string", "description": "self, exogenous, or marketplace"}
            },
            "required": ["claim", "falsifier"]
        }
    },
    "get_scoreboard": {
        "name": "get_scoreboard",
        "description": "Return published invalidation tracking. The fire-rate metric (falsified/total) shows whether falsifiers actually fire or are decorative.",
        "input_schema": {
            "type": "object",
            "properties": {}
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
        result = {"is_valid": bool(doc.get("pdb_id") and doc.get("timing_profile")), "version": "pdb-v1.1"}
    elif name == "falsify_check":
        result = falsify_check(arguments.get("claim", ""), arguments.get("evidence"))
    elif name == "preregister_falsifier":
        result = preregister_falsifier(
            arguments.get("claim", ""),
            arguments.get("falsifier", ""),
            arguments.get("window", {}),
            arguments.get("witness", "self")
        )
    elif name == "get_scoreboard":
        result = get_scoreboard()
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
            "serverInfo": {"name": "pdb-mcp-server", "version": "1.1.0"}
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


# ─── HTTP API Server ──────────────────────────────────────────────────────────

def run_http_server(port: int = 8080, api_key: str = ""):
    """Run as HTTP API server using Python's built-in http.server.
    
    Endpoints:
      GET  /health                      — Health check
      GET  /api/tools                   — List tools
      POST /api/tools/analyze-timing    — Timing scan
      POST /api/tools/generate-pdb      — PDB generation
      POST /api/tools/falsify-check     — Falsifier generation
      POST /api/tools/validate-pdb      — PDB validation
      GET  /api/schema                  — Return PDB schema JSON
    """
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import urlparse
    
    class PDBHTTPHandler(BaseHTTPRequestHandler):
        def _auth_check(self):
            if not api_key:
                return True
            auth = self.headers.get("Authorization", "")
            return auth == f"Bearer {api_key}" or auth == api_key
        
        def _send_json(self, data, status=200):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode())
        
        def _read_body(self) -> dict:
            length = int(self.headers.get("Content-Length", 0))
            if length == 0:
                return {}
            body = self.rfile.read(length)
            try:
                return json.loads(body.decode())
            except json.JSONDecodeError:
                return {}
        
        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/health":
                self._send_json({
                    "status": "ok",
                    "server": "pdb-mcp-server",
                    "version": "1.1.0",
                    "tools": ["analyze_timing", "generate_pdb", "falsify_check", "validate_pdb", "preregister_falsifier", "get_scoreboard", "get_schema"]
                })
            elif path == "/api/tools":
                result = handle_list_tools()
                self._send_json(result)
            elif path == "/api/scoreboard":
                self._send_json(get_scoreboard())
            elif path == "/api/schema":
                schema = _load_schema_safe()
                self._send_json(schema)
            else:
                self._send_json({"error": "Not found"}, 404)
        
        def do_POST(self):
            if not self._auth_check():
                self._send_json({"error": "Unauthorized"}, 401)
                return
            
            path = urlparse(self.path).path
            body = self._read_body()
            
            tool_map = {
                "/api/tools/analyze-timing": "analyze_timing",
                "/api/tools/generate-pdb": "generate_pdb",
                "/api/tools/falsify-check": "falsify_check",
                "/api/tools/validate-pdb": "validate_pdb",
                "/api/tools/preregister-falsifier": "preregister_falsifier",
                "/api/tools/get-scoreboard": "get_scoreboard",
                "/api/tools/get-schema": "get_schema",
            }
            
            tool_name = tool_map.get(path)
            if not tool_name:
                self._send_json({"error": f"Unknown endpoint: {path}"}, 404)
                return
            
            result = handle_call_tool(tool_name, body.get("arguments", body))
            self._send_json(result)
        
        def do_OPTIONS(self):
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            self.end_headers()
        
        def log_message(self, format, *args):
            if "--quiet" not in sys.argv:
                super().log_message(format, *args)
    
    server = HTTPServer(("0.0.0.0", port), PDBHTTPHandler)
    print(f"🌐 PDB MCP Server (HTTP) running on http://0.0.0.0:{port}")
    print(f"   Endpoints:")
    print(f"     GET  /health")
    print(f"     GET  /api/tools")
    print(f"     POST /api/tools/analyze-timing")
    print(f"     POST /api/tools/generate-pdb")
    print(f"     POST /api/tools/falsify-check")
    print(f"     POST /api/tools/preregister-falsifier")
    print(f"     POST /api/tools/validate-pdb")
    print(f"     GET  /api/scoreboard")
    print(f"     GET  /api/schema")
    if api_key:
        print(f"   Auth: Bearer token required")
    print(f"   Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.server_close()


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if "--test" in sys.argv:
        run_tests()
    elif "--http" in sys.argv:
        port = 8080
        api_key = os.environ.get("PDB_API_KEY", "")
        for i, arg in enumerate(sys.argv):
            if arg == "--port" and i + 1 < len(sys.argv):
                port = int(sys.argv[i + 1])
            if arg == "--api-key" and i + 1 < len(sys.argv):
                api_key = sys.argv[i + 1]
        run_http_server(port=port, api_key=api_key)
    else:
        run_stdio_server()
