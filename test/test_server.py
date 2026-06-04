"""Quick validation tests"""
import sys
sys.path.insert(0, '/tmp/pdb-mcp-tmp')
from pdb_server import analyze_timing, generate_pdb, falsify_check

data = {
    "hourly_distribution": [0]*8 + [2,5,8,12,15,10,8,5,3,1,0,0,0,0,0,0],
    "platform_activity": {"colony": 15, "moltr": 3, "github": 7}
}

r = analyze_timing(data)
assert r["status"] == "complete", f"FAIL: {r['status']}"

pdb = generate_pdb({"agent_id":"test","agent_name":"Test"}, data)
assert pdb["pdb_id"] != "", "No PDB ID"

f = falsify_check("peak activity in morning")
assert len(f["falsifiers"]) > 0, "No falsifiers"

print("All tests passed")
