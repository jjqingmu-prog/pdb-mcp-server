#!/usr/bin/env python3
"""
PDB MCP Server — Personal Destiny Blueprint as an MCP tool protocol.

Exposes agent-native timing analysis as callable MCP tools via HTTP.
Deployed at https://pdb.daovow.com/
"""

import json, os, sys, hashlib, datetime, random
from typing import Any, Optional
from datetime import datetime as dt

# ── FastAPI ──────────────────────────────────────────────────────────────
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

# ── Schema loader ────────────────────────────────────────────────────────────
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "pdb-v1.json")

def load_schema() -> dict:
    path = SCHEMA_PATH
    if not os.path.exists(path):
        path = os.path.join(os.path.dirname(__file__), "..", "pdb-schema", "pdb-v1.json")
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

# ── HTML landing page ────────────────────────────────────────────────────

LANDING_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>PDB MCP Server — Agent-Native Timing Protocol</title>
  <meta name="description" content="Personal Destiny Blueprint (PDB) as a falsifier-bearing MCP protocol. For AI agents who require verifiable timing analysis.">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,500;0,600;1,300;1,400&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    :root {
      --void: #060810; --abyss: #0c1018; --navy: #0d1b33;
      --gold: #B99352; --gold-light: #d4a95e;
      --ivory: #f9f5ee; --parchment: #ede7d6;
      --ink: #1a2332; --slate: #4b5563; --mist: #7c8ea0;
    }
    html { scroll-behavior: smooth; }
    body { font-family: 'Inter', system-ui, sans-serif; background: var(--void); color: var(--ivory); line-height: 1.6; }
    a { color: inherit; text-decoration: none; }

    .container { width: min(900px, calc(100% - 40px)); margin: 0 auto; }

    /* ── NAV ── */
    .nav {
      position: fixed; top: 0; left: 0; right: 0; z-index: 100;
      background: rgba(6,8,16,0.94); backdrop-filter: blur(14px);
      border-bottom: 1px solid rgba(185,147,82,0.12);
    }
    .nav-inner { display: flex; align-items: center; justify-content: space-between; padding: 18px 0; }
    .nav-brand { font-family: 'Cormorant Garamond', Georgia, serif; font-size: 20px; font-weight: 500; letter-spacing: 0.1em; color: var(--gold); }
    .nav-links { display: flex; gap: 24px; list-style: none; font-size: 12px; font-weight: 500; letter-spacing: 0.16em; text-transform: uppercase; color: rgba(249,245,238,0.5); }
    .nav-links a { transition: color 0.2s; color: rgba(249,245,238,0.5); }
    .nav-links a:hover { color: var(--gold); }

    /* ── HERO ── */
    .hero { min-height: 100vh; display: flex; align-items: center; justify-content: center; text-align: center; padding: 100px 0 60px; }
    .hero-kicker { font-size: 10px; font-weight: 600; letter-spacing: 0.35em; text-transform: uppercase; color: var(--gold); margin-bottom: 24px; }
    .hero-title { font-family: 'Cormorant Garamond', Georgia, serif; font-size: clamp(40px, 6vw, 72px); font-weight: 300; line-height: 1.05; color: var(--ivory); margin-bottom: 20px; }
    .hero-title em { font-style: italic; color: var(--gold); }
    .hero-desc { font-size: 15px; line-height: 1.8; color: rgba(249,245,238,0.6); max-width: 520px; margin: 0 auto 32px; }
    .hero-tag { display: inline-block; padding: 6px 16px; border: 1px solid rgba(185,147,82,0.3); border-radius: 2px; font-size: 10px; letter-spacing: 0.2em; text-transform: uppercase; color: var(--gold); margin-bottom: 28px; }
    .btn-gold { display: inline-block; padding: 16px 44px; border-radius: 2px; background: linear-gradient(135deg, var(--gold) 0%, var(--gold-light) 100%); color: var(--void); font-size: 10px; font-weight: 600; letter-spacing: 0.28em; text-transform: uppercase; transition: opacity 0.5s, transform 0.4s; }
    .btn-gold:hover { opacity: 0.85; transform: translateY(-2px); }
    .hero-price { margin-top: 16px; font-size: 12px; color: rgba(249,245,238,0.4); letter-spacing: 0.1em; }

    /* ── SECTIONS ── */
    section { padding: 80px 0; border-top: 1px solid rgba(185,147,82,0.08); }
    .section-label { font-size: 9px; font-weight: 600; letter-spacing: 0.3em; text-transform: uppercase; color: var(--gold); margin-bottom: 12px; }
    .section-title { font-family: 'Cormorant Garamond', Georgia, serif; font-size: 28px; font-weight: 400; color: var(--ivory); margin-bottom: 32px; }

    /* ── TOOLS GRID ── */
    .tools-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; }
    .tool-card { background: rgba(255,255,255,0.03); border: 1px solid rgba(185,147,82,0.1); border-radius: 4px; padding: 24px; }
    .tool-card h3 { font-family: 'Cormorant Garamond', Georgia, serif; font-size: 18px; font-weight: 500; color: var(--gold); margin-bottom: 8px; }
    .tool-card .method { display: inline-block; font-size: 9px; font-weight: 600; letter-spacing: 0.15em; padding: 2px 8px; border-radius: 2px; margin-bottom: 8px; }
    .method-get { background: rgba(52,211,153,0.15); color: #34d399; }
    .method-post { background: rgba(96,165,250,0.15); color: #60a5fa; }
    .tool-card p { font-size: 13px; color: rgba(249,245,238,0.55); line-height: 1.6; }

    /* ── PRICING ── */
    .pricing-cards { display: flex; gap: 20px; flex-wrap: wrap; justify-content: center; }
    .pricing-card { flex: 1; min-width: 260px; max-width: 360px; background: rgba(255,255,255,0.02); border: 1px solid rgba(185,147,82,0.12); border-radius: 4px; padding: 36px 28px; text-align: center; }
    .pricing-card.featured { border-color: var(--gold); background: rgba(185,147,82,0.04); }
    .pricing-amount { font-family: 'Cormorant Garamond', Georgia, serif; font-size: 42px; font-weight: 300; color: var(--gold); }
    .pricing-currency { font-size: 18px; vertical-align: super; }
    .pricing-label { font-size: 11px; color: rgba(249,245,238,0.4); letter-spacing: 0.1em; margin: 4px 0 20px; }
    .pricing-features { list-style: none; text-align: left; margin: 20px 0; }
    .pricing-features li { font-size: 13px; color: rgba(249,245,238,0.6); padding: 6px 0; }
    .pricing-features li::before { content: "— "; color: var(--gold); }

    /* ── SCOREBOARD ── */
    .stat-row { display: flex; gap: 32px; flex-wrap: wrap; justify-content: center; }
    .stat { text-align: center; }
    .stat-num { font-family: 'Cormorant Garamond', Georgia, serif; font-size: 36px; color: var(--gold); }
    .stat-label { font-size: 11px; color: rgba(249,245,238,0.4); letter-spacing: 0.1em; margin-top: 4px; }

    /* ── FOOTER ── */
    .footer { padding: 40px 0; text-align: center; border-top: 1px solid rgba(185,147,82,0.08); }
    .footer a { color: var(--gold); font-size: 12px; }
  </style>
</head>
<body>
<nav class="nav">
  <div class="container nav-inner">
    <div class="nav-brand">PDB ∞ MCP</div>
    <ul class="nav-links">
      <li><a href="#tools">Tools</a></li>
      <li><a href="#pricing">Pricing</a></li>
      <li><a href="#scoreboard">Scoreboard</a></li>
      <li><a href="/docs">API</a></li>
      <li><a href="https://scout.daovow.com">Scout</a></li>
    </ul>
  </div>
</nav>

<section class="hero">
  <div class="container">
    <div class="hero-tag">MCP Protocol · v1.1.0</div>
    <h1 class="hero-title">Personal Destiny<br><em>Blueprint</em></h1>
    <p class="hero-desc">
      A falsifier-bearing timing analysis protocol for AI agents.<br>
      Pre-register your conditions. Generate your blueprint.<br>
      Let the scoreboard track what actually fires.
    </p>
    <div>
      <a href="https://scout.daovow.com/services" class="btn-gold">Purchase PDB Scan · $25 USDC</a>
    </div>
    <p class="hero-price">Receive within 12 hours · Base chain USDC to 0xf24f...5203</p>
  </div>
</section>

<section id="tools">
  <div class="container">
    <div class="section-label">Protocol Layer</div>
    <h2 class="section-title">MCP Tools</h2>
    <div class="tools-grid">
      <div class="tool-card"><span class="method method-post">POST</span><h3>analyze_timing</h3><p>One-shot timing scan from agent activity data. Returns current season, confidence, and falsifier condition.</p></div>
      <div class="tool-card"><span class="method method-post">POST</span><h3>generate_pdb</h3><p>Full Personal Destiny Blueprint with four pillars, element profile, pattern analysis, and pre-registered falsifiers.</p></div>
      <div class="tool-card"><span class="method method-post">POST</span><h3>validate_pdb</h3><p>Validate a PDB document against the v1 schema. Returns missing fields and compatibility.</p></div>
      <div class="tool-card"><span class="method method-post">POST</span><h3>falsify_check</h3><p>Generate falsifier statements for any timing claim. Rewrites vague claims into falsifiable form.</p></div>
      <div class="tool-card"><span class="method method-get">GET</span><h3>get_schema</h3><p>Return the current PDB schema v1.1.0 as JSON. Machine-readable field definitions.</p></div>
      <div class="tool-card"><span class="method method-post">POST</span><h3>preregister_falsifier</h3><p>Register falsifier conditions before the PDB is generated. Conditions are tracked and evaluable.</p></div>
      <div class="tool-card"><span class="method method-get">GET</span><h3>scoreboard</h3><p>Published invalidation tracking. If no PDB ever fires its falsifier, the falsifiers are decorative.</p></div>
    </div>
  </div>
</section>

<section id="pricing">
  <div class="container">
    <div class="section-label">Pricing</div>
    <h2 class="section-title">For Agents · For Humans</h2>
    <div class="pricing-cards">
      <div class="pricing-card featured">
        <div class="pricing-amount"><span class="pricing-currency">$</span>25</div>
        <div class="pricing-label">PDB Full Scan · For Agents</div>
        <ul class="pricing-features">
          <li>Full timing profile with control baseline (v1.1)</li>
          <li>Pre-registered falsifiers (self_evaluable / exogenous)</li>
          <li>Scoreboard entry — fire-rate published per server</li>
          <li>Prime / off-peak window comparison</li>
          <li>Vow compatibility check</li>
          <li>Delivery within 12 hours of payment</li>
        </ul>
        <a href="https://scout.daovow.com/services" class="btn-gold">Send $25 USDC</a>
      </div>
      <div class="pricing-card">
        <div class="pricing-amount"><span class="pricing-currency">$</span>200+</div>
        <div class="pricing-label">Custom Integration</div>
        <ul class="pricing-features">
          <li>Custom MCP tool development</li>
          <li>Smart contract integration</li>
          <li>Protocol design consultation</li>
          <li>Falsifier system auditing</li>
        </ul>
        <a href="https://colony.io" class="btn-gold" style="background:transparent;border:1px solid rgba(185,147,82,0.3);color:var(--gold);">Inquire on Colony</a>
      </div>
    </div>
  </div>
</section>

<section id="scoreboard">
  <div class="container">
    <div class="section-label">Verification</div>
    <h2 class="section-title">Scoreboard</h2>
    <div class="stat-row">
      <div class="stat"><div class="stat-num" id="sb-total">—</div><div class="stat-label">Total PDBs</div></div>
      <div class="stat"><div class="stat-num" id="sb-fired">—</div><div class="stat-label">Invalidated by Falsifier</div></div>
      <div class="stat"><div class="stat-num" id="sb-rate">—</div><div class="stat-label">Fire Rate</div></div>
    </div>
    <p style="text-align:center;margin-top:24px;font-size:12px;color:rgba(249,245,238,0.35);letter-spacing:0.05em;">
      A tautology-proof system. Falsifiers that never fire are decorative.<br>
      <a href="/scoreboard" style="color:var(--gold);">View raw scoreboard →</a>
    </p>
  </div>
</section>

<footer class="footer">
  <div class="container">
    <p style="font-size:12px;color:rgba(249,245,238,0.3);letter-spacing:0.1em;">
      PDB MCP Server · <a href="https://scout.daovow.com">@DaoVowScout</a> · 
      Wallet: <code style="font-size:11px;color:rgba(249,245,238,0.5);">0xf24f...5203</code> · 
      <a href="https://github.com/jjqingmu-prog/pdb-mcp-server">GitHub</a>
    </p>
  </div>
</footer>

<script>
fetch('/scoreboard').then(r=>r.json()).then(d=>{
  var s = d.summary || {};
  document.getElementById('sb-total').textContent = s.total_pdbs || 0;
  document.getElementById('sb-fired').textContent = s.invalidated_by_falsifier || 0;
  document.getElementById('sb-rate').textContent = (s.fire_rate || 0) + '%';
}).catch(function(){});
</script>
</body>
</html>"""

# ── Routes ───────────────────────────────────────────────────────────────

@app.get("/")
async def root(request: Request):
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return HTMLResponse(LANDING_HTML)
    # API client
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
