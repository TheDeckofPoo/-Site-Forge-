# CP4 Sawtooth Apply/Build Debug

**Machine:** ORNCCP4  
**RUN:** `workspace/cp4-run/RUN`  
**Date:** 2026-09-13  
**Firewall:** finished PLC4 never used as generation input

---

## Exact failure (reproduced)

| Layer | Result |
|-------|--------|
| **Preflight UI readiness** | **FAIL** — Sawtooth stays `REVIEW_REQUIRED` because `configuration_required` contains `discharge_conveyor` |
| **Apply (`#btn-saw-save`)** | Stores workbook but does **not** set READY when `unresolved > 0` |
| **Build PLC preflight** | Blocks Export: `Sawtooth: DETECTED — REVIEW REQUIRED — 1 unresolved` |
| **CLI pack emit** | **OK** when workbook has `sawtooth_build` + `--include-programs Sawtooth_Merge` |
| **`generation_assertions`** | **OK** (`failures: []`) — `Sawtooth_Merge` present in programs/gold_programs |

CLI repro (workbook with SiteModel-shaped `sawtooth_build`, discharge not blocking):

```text
python fortna_autogen.py from-run \
  --run-dir workspace/cp4-run/RUN \
  --workbook exports/plc2-validation/_sawtooth_apply_wb.json \
  --include-programs Sawtooth_Merge \
  --out-dir exports/plc2-validation/cp4-sawtooth-apply-repro
```

Report: `programs` includes `Sawtooth_Merge`; `generation_assertions.ok=true`.

**Conclusion:** failure is **preflight UI readiness / Apply gate**, not pack emit or generation assertions.

---

## Trace

```
discover_sawtooth / build_sawtooth_merge_model
  → model_to_editor_shape (editors.sawtooth)
  → sawtoothBuildFromSiteModel (dashboard)
  → persistSawtoothToWorkbook
  → Apply (#btn-saw-save)  ← blocked READY by discharge_conveyor
  → runAutogenGenerate / preflight  ← blocks Export
```

Before fix:

- `build_sawtooth_merge_model` left `discharge_conveyor` as `UNRESOLVED` (hardcoded “No Convpath successor”) and did **not** list it in merge `unresolved[]`.
- `model_to_editor_shape` → `configuration_required: []`, `downstream_conveyor: null`.
- `sawtoothBuildFromSiteModel` **forced** `discharge_conveyor` into `configuration_required` whenever downstream was empty.
- Apply therefore never reached READY even though collector `P414`, encoder `ENC414`, and 5 lanes were filled from RUN.

---

## Encoder proof — ENC414 vs ENC424

Source: `FORTNA/Encoders.asc.ORNCCP4` + discovery associations.

| Encoder | EnableBit | Jamzone | Associations | Role |
|---------|-----------|---------|--------------|------|
| **ENC414** | `VFD414_AUX` | `SAWTOOTH MERGE` | `encoder_enable_vfd→VFD414_AUX`, `encoder_to_saw_merge_via_motor_io→SAWTOOTH_MERGE`, `encoder_jamzone_sawtooth` | **Collector tracking** for Sawtooth merge |
| **ENC424** | `VFD424_AUX` | `CITY COUNTER` | `encoder_enable_vfd→VFD424_AUX` only | **City counter / CITY_LANE** — not sawtooth collector |

SiteModel sorter rows corroborate: `SAWTOOTH_MERGE.encoder_io=ENC414`, `CITY_LANE.encoder_io=ENC424`.

SawMerge.MotorIO = `VFD414_AUX` → collector `P414` (RUN_DERIVED) matches ENC414 digits/enable.

---

## Unresolved field classification (A/B/C/D)

| Field | Pre-fix value | Class | Notes |
|-------|--------------|-------|-------|
| `collector_conveyor` | `P414` | — resolved | RUN_DERIVED from SawMerge.MotorIO `VFD414_AUX` |
| `merge_encoder` / `collector_encoder` | `ENC414` | — resolved | RUN_DERIVED via MotorIO + Jamzone/associations |
| `discharge_conveyor` / `downstream` | was null | **A — parser miss** | RUN already has Mtrchain `VFD414_EN`: Motor_Chained1=`P414`, Motor_Chained2=`P416`. Prior acceptance / knowledge enrich already treated **P416** as downstream. Merge model hardcoded UNRESOLVED. |
| Lane `jam_pe` (all 5) | null | **D — optional** | No SawLane jam PE column; correctly excluded from blocking `configuration_required` |
| Area / ES zone | unknown | **C — genuine unknown** | `exports/cp4-discovery/unknowns.json` — engineer config; not a Sawtooth Apply blocker |
| Lane conveyor / PE / drive / slice / reserve | filled | — resolved | RUN_EXPLICIT from SawLane |
| Timings (`clctr_speed_fpm`, etc.) | 0 / empty | **D — optional** | Not invented; pack defaults / engineer CFG |

No class **B (doc derive)** gaps blocked Apply for this site after A was fixed.

---

## Root cause

1. **Primary:** `sawtoothBuildFromSiteModel` treated missing discharge as a **blocking** Apply field while `build_sawtooth_merge_model` failed to parse Mtrchain successor `P416` already present in RUN.
2. **Secondary:** Python bridges (`site_model_to_sawtooth_build`, `build_sawtooth_editor_v2`) also counted “downstream conveyor” as configuration-required, so CLI/workbook paths could keep the same soft-fail even when collector+encoder+lanes were complete.

Pack generation itself was fine once `Sawtooth_Merge` was included.

---

## Fix applied (minimal)

1. **`fortna_sawtooth_merge_model.py`** — derive `discharge_conveyor` from Mtrchain: next `Motor_Chained*` P-tag after collector on the collector VFD row → **P416** (`RUN_DERIVED`).
2. **`dashboard/fortna-plus.js`** — do not force `discharge_conveyor` / jam PE into blocking `configuration_required`; only collector + merge encoder are hard Apply gates.
3. **`fortna_sitemodel_to_autogen.py`** / **`fortna_knowledge_enrich.py`** — align: downstream optional for readiness counting.
4. **`test_sawtooth_merge_model_cp4.py`** — assert discharge `P416`.

Post-fix: editor `downstream_conveyor=P416`, JS unresolved `[]` → Apply READY; CLI continues to emit `Sawtooth_Merge`.

---

## Recommended follow-ups (not done here)

- Fullline `EZPE418_F` / `Response IO=VFD414_EN` / `Conveyor_Name=P418` is separate accum feedback evidence; do **not** silently replace P416 with P418 without an engineer/transport decision (DEV Prefill historically used P418).
- Transport confirmed edges currently omit P414→P416/P418; geometry freeze may need a later pass (outside this Apply fix).
- Sorter `CITY_LANE` remains `NOT_SUPPORTED` — correctly excluded from Export preflight.
