# Safety evidence semantics (corpus fact-finding)

**Status:** OBSERVED_ONLY / SOURCE_PROVEN where noted. No zone assignment from this doc.

## Device classification (not zone membership)

Corpus name patterns observed in `evidence.io_claims` / Configio Desc:

| Category | Evidence class | Notes |
|----------|----------------|-------|
| E_STOP | OBSERVED_ONLY | ESTOP / E-STOP tokens in I/O names |
| ESLS | OBSERVED_ONLY | ESLS tokens common |
| RESET | OBSERVED_ONLY | RESET tokens; may be area-level |
| ESR | OBSERVED_ONLY | weaker / ambiguous vs ESTOP substrings |
| MCR | OBSERVED_ONLY | MCR tokens when present |
| CS | OBSERVED_ONLY | CS# / control station forms — high false-positive risk |
| OTHER_SAFETY | OBSERVED_ONLY | SAFE / GATE tokens |

## Rules

- Engineer zone membership is **human intent** — never invented from name taxonomy.
- `PROVEN` membership only from RUN-proven links or ENGINEER_ASSIGNED after Apply.
- Classifier omissions → Safety Build FOUND under-count → field REVIEW, not silent invent.

See `exports/research/safety_device_taxonomy.json` for pattern inventory.
