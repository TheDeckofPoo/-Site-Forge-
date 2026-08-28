# Site Twin (Site Forge ↔ PRISM ↔ SpaceXAI)

## Where in the UI

**PLC Autogen** tab → left column → **Site Twin · Gaps**

- **Refresh** — load `twin_gaps.json` from last export or PRISM  
- **Search PRISM** — similar gold / peer snippets  
- **Propose gap-fill** — SpaceXAI (`XAI_API_KEY`) or PRISM heuristics  
- **Apply approved** — patch `workspace/autogen_workbook.json` → Export L5X again  

## Files

| Path | Role |
|------|------|
| `exports/autogen/<run>/twin_gaps.json` | Gaps from Generate |
| `PRISM/.../twin/gaps.json` | Staged twin |
| `tools/scripts/fortna_prism_twin.py` | Bridge CLI |

## Rule

AI proposes workbook patches only — never silent L5X rewrites.
