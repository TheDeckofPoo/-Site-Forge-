# UI status summary (`site_model.ui_status_summary`)

Compact JSON produced by `fortna_knowledge_enrich.ui_status_summary` after enrichment.
Dashboard status cards for TRANSPORT / SAWTOOTH / SORTER should read this object
(or the same fields on `exports/knowledge-integration/summary.json`).

Wiring note: prefer rendering helpers that consume this shape; do not invent
site-constant labels. Electron preload / `fortna-plus.js` may surface it when
the active site model is loaded.

---

## Shape

```json
{
  "TRANSPORT": {
    "Included": 0,
    "Available": 0,
    "Excluded": 0,
    "relationships_need_review": 0
  },
  "SAWTOOTH": {
    "detected": 0,
    "lanes": 0,
    "configuration_resolved_pct": null,
    "engineer_decisions": null
  },
  "SORTER": {
    "detected": 0,
    "configuration_modeled": false,
    "encoder_resolved": false,
    "scan_zones_resolved": false,
    "divert_map_required": true,
    "generation": "none"
  },
  "PE": {
    "auto_resolved": 0,
    "engineer_required": 0
  }
}
```

| Card | Fields to show |
|------|----------------|
| TRANSPORT | Included / Available / Excluded; relationships needing review |
| SAWTOOTH | detected, lanes, configuration_resolved_pct, engineer_decisions |
| SORTER | detected, encoder_resolved, scan_zones_resolved, generation (`none` \| `partial`) |
| PE (optional) | auto_resolved vs engineer_required |

`SORTER.generation` stays `partial` at most until divert / tracking / WCS leaves are supported.
`divert_map_required` is currently always `true` for honesty.

---

## Source

- Builder: `tools/scripts/fortna_knowledge_enrich.py` → `ui_status_summary()`
- Attached on site dict as `site["ui_status_summary"]` by `enrich_site_model()`
