# CP4 Compiler Pass 2

**Branch:** eature/cp4-compiler-pass2  
**Finished PLC4 used:** NO

## Fixes
- Generic identity matching (ortna_identity) — P120 does not imply P1200
- Realization reconciles 76 discovery mechanical = 76 generated (**ACCEPTED**)
- Explicit Sawtooth parameter map (ortna_sawtooth_param) — no arbitrary L5X mangling
- UX: no CP4-specific top-level buttons; Advanced / Evidence only

## Outputs
exports/cp4-pass2/ — see generation_summary.json

## Workflow (unchanged)
Import RUN → Auto Build → Review / Correct → Apply to Autogen → Build PLC
