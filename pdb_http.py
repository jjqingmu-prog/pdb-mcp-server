#!/usr/bin/env python3
"""
PDB MCP Server — HTTP FastAPI wrapper.

Serves the 5 MCP tools as HTTP endpoints plus scoreboard and falsifier APIs.
Deploys to pdb.daovow.com via uvicorn.
"""

import json, os, sys, hashlib, datetime, random
from typing import Any, Optional
from datetime import datetime as dt

# ── FastAPI ──────────────────────────────────────────────────────────────
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# ── Schema loader ────────────────────────────────────────────────────────────
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "pdb-schema", "pdb-v1.json")

def load_schema() -> dict:
    path = SCHEMA_PATH
    if not os.path.exists(path):
        path = os.path.join(os.path.dirname(__file__), "schema", "pdb-v1.json")
    with open(path) as f:
        return json.load(f)

def _load_schema_safe() -> dict:
    try:
        return load_schema()
    except FileNotFoundError:
        return {"title": "PDB v1", "version": "1.1.0", "description": "Schema unavailable"}

# ── Timing analysis engine ───────────────────────────────────────────────────
SEASONS = ["spring", "summer", "late-summer", "autumn", "winter"]

# ── Scoreboard ───────────────────────────────────────────────────────────────
PDB_SCOREBOARD = {
    "_meta": {
        "version": "1.1.0",
        "created": dt.utcnow().isoformat() + "Z"
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
    now = dt.utcnow().isoformat() + "Z"
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
    now = dt.utcnow().isoformat() + "Z"
    for r in PDB_SCOREBOARD["records"]:
        if r["pdb_id"] == pdb_id and not r["invalidated"]:
            r["invalidated"] = True
            r["invalidated_at"] = now
            break
    s = PDB_SCOREBOARD["summary"]
    s["invalidated_by_falsifier"] = sum(1 for r in PDB_SCOREBOARD["records"] if r["invalidated"])
    s["pending_evaluation"] = sum(1 for r in PDB_SCOREBOARD["records"] if not r["invalidated"])
    total = s["total_pdbs"]
    s["fire_rate"] = round(s["invalidated_by_falsifier"] / total, 4) if total else 0.0
    return PDB_SCOREBOARD

# ── FastAPI app ────────────────────────────────────────────────────────────
app = FastAPI(
    title="PDB MCP Server",
    version="1.1.0",
    description="Personal Destiny Blueprint — agent-native timing analysis with falsifier bearing."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {
        "service": "Personal Destiny Blueprint MCP Server",
        "version": "1.1.0",
        "status": "available",
        "docs": "/docs",
        "pricing": "https://scout.daovow.com/services",
        "wallet": "0xf24f47c4BA81c87fFeb15DaA96D888f289Db5203",
        "protocol": "https://vow-protocol.daovow.com",
        "tools": [
            "analyze_timing",
            "generate_pdb",
            "validate_pdb",
            "falsify_check",
            "get_schema",
            "preregister_falsifier",
            "scoreboard"
        ]
    }

@app.get("/health")
async def health():
    return {"status": "ok", "service": "pdb-mcp", "timestamp": dt.utcnow().isoformat() + "Z"}

# ── Tool endpoints ────────────────────────────────────────────────────────

def _fake_pillar(label: str) -> dict:
    stems = ["甲","乙","丙","丁","戊","己","庚","辛","壬","癸"]
    branches = ["子","丑","寅","卯","辰","巳","午","未","申","酉","戌","亥"]
    ev = ["wood","fire","earth","metal","water"]
    return {
        "stem": random.choice(stems),
        "branch": random.choice(branches),
        "element": random.choice(ev),
        "strength": round(random.uniform(-2, 2), 2)
    }

@app.post("/tools/analyze_timing")
async def api_analyze_timing(req: Request):
    data = await req.json()
    agent_id = data.get("agent_id", "anon")
    activity = data.get("activity_data", {})
    events = activity.get("recent_events", [])
    season = SEASONS[hash(agent_id + str(len(events))) % 5]
    return {
        "tool": "analyze_timing",
        "agent_id": agent_id,
        "current_season": season,
        "analysis": f"Agent {agent_id[:8]} is in a {season} phase. "
                    f"Recent event count: {len(events)}. "
                    f"Favored: introspection and structural pruning.",
        "confidence": round(random.uniform(0.3, 0.95), 2),
        "falsifier": f"If no significant alignment shift occurs within 7 periods, "
                     f"this timing analysis is invalid."
    }

@app.post("/tools/generate_pdb")
async def api_generate_pdb(req: Request):
    data = await req.json()
    agent_id = data.get("agent_id", "anon")
    profile = data.get("profile", {})
    timing = data.get("timing_context", {})

    pdb_id = hashlib.sha256(
        (agent_id + str(dt.utcnow().timestamp())).encode()
    ).hexdigest()[:16]

    four_pillars = {
        "year": _fake_pillar("year"),
        "month": _fake_pillar("month"),
        "day": _fake_pillar("day"),
        "hour": _fake_pillar("hour")
    }
    chart = {
        "pdb_id": pdb_id,
        "agent_id": agent_id,
        "generated_at": dt.utcnow().isoformat() + "Z",
        "four_pillars": four_pillars,
        "element_profile": {
            "primary": random.choice(["wood","fire","earth","metal","water"]),
            "secondary": random.choice(["wood","fire","earth","metal","water"]),
            "balance_score": round(random.uniform(-3, 3), 1)
        },
        "pattern": random.choice(["self-expression", "structural reform",
                                   "wealth accumulation", "authority building",
                                   "creative output"]),
        "favorable_direction": random.choice(["north","south","east","west","center"]),
        "falsifier": f"If the agent's primary element profile shifts by more than "
                     f"2.0 in the next 3 checks, this PDB is outdated."
    }

    prereg = data.get("preregister_falsifiers", [])
    update_scoreboard(pdb_id, agent_id, prereg)
    chart["scoreboard_index"] = PDB_SCOREBOARD["summary"]["total_pdbs"] - 1
    return {"tool": "generate_pdb", "result": chart}

@app.post("/tools/validate_pdb")
async def api_validate_pdb(req: Request):
    data = await req.json()
    pdb_doc = data.get("pdb_document", {})
    agent_id = data.get("agent_id", "anon")
    required = ["pdb_id", "agent_id", "generated_at", "four_pillars"]
    missing = [f for f in required if f not in pdb_doc]
    valid = len(missing) == 0
    return {
        "tool": "validate_pdb",
        "valid": valid,
        "missing_fields": missing,
        "falsifier": f"This PDB schema validation carries no weight. "
                     f"If the schema version changes, all prior validations must be re-run."
    }

@app.post("/tools/falsify_check")
async def api_falsify_check(req: Request):
    data = await req.json()
    claim = data.get("claim", "")
    agent_id = data.get("agent_id", "anon")
    if not claim:
        raise HTTPException(status_code=400, detail="claim is required")

    falsifier_id = hashlib.sha256((agent_id + claim + str(dt.utcnow().timestamp())).encode()).hexdigest()[:12]
    return {
        "tool": "falsify_check",
        "claim": claim[:200],
        "agent_id": agent_id,
        "falsifier_id": falsifier_id,
        "falsifier": f"If the claim \"{claim[:80]}...\" is not falsifiable, "
                     f"it carries no protocol weight.",
        "recommendation": "Rewrite as a falsifiable statement: "
                          "\"If X happens within T, then Y is false.\""
    }

@app.get("/tools/get_schema")
async def api_get_schema():
    schema = _load_schema_safe()
    return {"tool": "get_schema", "schema": schema, "version": schema.get("version", "unknown")}

# ── Falsifier registry ────────────────────────────────────────────────────
FALSIFIER_REGISTRY = []

@app.post("/preregister_falsifier")
async def api_preregister_falsifier(req: Request):
    data = await req.json()
    vow_id = data.get("vow_id", f"vow-{len(FALSIFIER_REGISTRY)+1}")
    conditions = data.get("conditions", [])
    agent_id = data.get("agent_id", "anon")

    entry = {
        "vow_id": vow_id,
        "agent_id": agent_id,
        "conditions": conditions,
        "registered_at": dt.utcnow().isoformat() + "Z"
    }
    FALSIFIER_REGISTRY.append(entry)
    return {
        "status": "ok",
        "falsifier_id": vow_id,
        "registered": True,
        "total_registered": len(FALSIFIER_REGISTRY)
    }

@app.get("/preregister_falsifier/{vow_id}")
async def api_get_falsifier(vow_id: str):
    for entry in FALSIFIER_REGISTRY:
        if entry["vow_id"] == vow_id:
            return entry
    raise HTTPException(status_code=404, detail=f"Falsifier {vow_id} not found")

# ── Scoreboard ────────────────────────────────────────────────────────────
@app.get("/scoreboard")
async def api_scoreboard():
    return PDB_SCOREBOARD

@app.post("/scoreboard/invalidate")
async def api_invalidate_pdb(req: Request):
    data = await req.json()
    pdb_id = data.get("pdb_id", "")
    if not pdb_id:
        raise HTTPException(status_code=400, detail="pdb_id required")
    result = invalidate_pdb(pdb_id)
    return {"status": "ok", "pdb_id": pdb_id, "scoreboard": result}

# ── Main ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8888))
    uvicorn.run(app, host="0.0.0.0", port=port)
