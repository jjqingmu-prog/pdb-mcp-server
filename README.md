# PDB MCP Server

> **Personal Destiny Blueprint as an MCP tool protocol.**

Exposes falsifier-bearing timing analysis as callable MCP tools for any MCP-compatible agent client.

## Tools

| Tool | Description |
|:---|---|
| `analyze_timing` | One-shot timing scan from agent activity data |
| `generate_pdb` | Build a full PDB document from agent profile + timing |
| `validate_pdb` | Validate a PDB document against schema v1 |
| `falsify_check` | Generate falsifier statements for a timing claim |
| `get_schema` | Return the current PDB schema as JSON |

## Usage

```bash
pip install mcp
python3 pdb_server.py --test  # run self-tests
```

## Protocol

Implements the Model Context Protocol (MCP) over stdio:
- `tools/list` → 5 tools
- `tools/call` → JSON-RPC tool invocation

## Related

- [/vow Protocol](https://github.com/jjqingmu-prog/vow-protocol)
- [PDB Schema](https://github.com/jjqingmu-prog/pdb-schema)
