# Demo: NTP scaffold + spare placeholder safety

**Branch:** `demo/reno-ship-sorter-readiness`  
**START SHA:** `a935a22a86f93dceb0f3910d9f5c8f506a0c1a27`
**FINAL SHA:** `817acb2ac0047b17c5c54f53e17c462e296dbf2a`  
**Mission:** PHASE 7 (NTP generic) + PHASE 9 (spare output safety)

---

## PHASE 7 — NTP generic scaffold

### Before

`_build_sys_comm_program_xml` emitted NTP as:

```
NOP();
REVIEW_REQUIRED — NTP/SNTP not yet generically emitible from
OReilly_Library_v3 + RUN alone (finished System_Program.L5X quarantined)
```

No `SNTP_*` controller tags, no `SNTP_AOI_TAG`, no `AOI_SNTP_QUERY(...)` call.

Gold Pick L5X (`MSCRENOPICK_2026_10_13_1725.L5X`) contains `AOI_SNTP_QUERY` definition (library AOI) but not a live System/NTP instance scaffold in that export. Finished Greensboro PLC2/4/5 use the same AOI call shape (validation oracle only — not production source).

### After (generic rule)

When NTP/System is included **and** library has `AOI_SNTP_QUERY` + `AOI_TIME_ADD` + `AOI_TIME_DIFFERENCE` + `SKT_UDP_DATA`:

| Artifact | Emit |
|----------|------|
| Program tag | `SNTP_AOI_TAG : AOI_SNTP_QUERY` (`Enable_Instruction=0`) |
| Controller tags | `SNTP_SERVER_ADDRESS`, `SNTP_TIME_RETRIEVED`, `SNTP_MSG_DATA`, `SNTP_MSG_CREATE`, `SNTP_MSG_OPEN`, `SNTP_MSG_WRITE`, `SNTP_MSG_READ`, `SNTP_MSG_DELETE` |
| Routine | `AOI_SNTP_QUERY(SNTP_AOI_TAG,SNTP_TIME_RETRIEVED,SNTP_SERVER_ADDRESS,SNTP_MSG_DATA,SNTP_MSG_CREATE,SNTP_MSG_OPEN,SNTP_MSG_WRITE,SNTP_MSG_READ,SNTP_MSG_DELETE);` |

Server address resolution (generic, site evidence only):

1. `options.ntp_server` / `sntp_server` / `sntp_server_address` / `ntp_server_address`
2. else RUN `SystemFiles/ntp.conf` uncommented `server <host>`
3. else empty → **CONFIG_REQUIRED** / safely disabled

**Forbidden shortcut check:** PASS — does **not** cookie-cut quarantined `System_Program.L5X`, does **not** hardcode Greensboro IP/hostname. `SNTP_MSG_*` `ConnectionPath` starts as `ENET_PENDING` and is rewritten to proven ENET (existing gate).

Status meanings:

| Condition | `ntp_emit.status` | `commissioning_ready` |
|-----------|-------------------|------------------------|
| No site server | `CONFIG_REQUIRED` | `false` |
| Site server present | `SCAFFOLD_SERVER_PRESENT` | `false` (Enable_Instruction still 0) |
| Library deps missing | `REVIEW_REQUIRED` | `false` |

---

## PHASE 9 — Spare output safety

### Hazard (before)

IO_MAP unused-bit fill emitted:

```
XIC(CPxRIOn:I.Data[s].b)OTE(NO_PointPlaceholder);   # spare input
XIC(NO_PointPlaceholder)OTE(CPxRIOn:O.Data[s].b);    # spare output
```

Any spare **input** going TRUE set the shared BOOL, which then energized **all** spare **outputs**. Proven energizable hazard.

### Fix (after)

| Direction | Emit |
|-----------|------|
| Spare **input** | `XIC(channel)OTE(NO_PointPlaceholder);` (soft BOOL documentation only) |
| Spare **output** | `NOP();` with comment documenting channel — **no functional writer** |

`NO_PointPlaceholder` tag is created only when spare inputs exist. Shared-BOOL must not drive physical outputs.

Report fields:

- `io_map_spare_outputs_documented`
- `io_map_spare_output_safety`

---

## Files changed

- `tools/scripts/fortna_autogen.py` — NTP scaffold helpers + spare-output NOP emit
- `tests/compiler/test_demo_ntp_spare_safety.py` — unit checks
- `exports/diagnostics/demo_ntp_spare_report.md` — this report

---

## Tests run

```
python tests/compiler/test_demo_ntp_spare_safety.py
→ PASS: demo_ntp_spare unit checks
```

Coverage:

- resolve NTP from options / RUN ntp.conf / commented-only → empty
- CONFIG_REQUIRED scaffold without server (AOI call + empty STRING + all SNTP_* tags)
- server present still not commissioning-ready
- source no longer contains `XIC(NO_PointPlaceholder)OTE({channel})`

---

## KNOWN REMAINING FAILURES

- NTP scaffold is **not** commissionable until site server + `Enable_Instruction` + proven ENET path are set by commissioning.
- Sites that emit `SNTP_MSG_*` without a proven Ethernet module still hit the existing Studio blocker (`SNTP_MSG_*` ConnectionPath gate) — intentional fail-closed.
- Full site L5X regen / Warden acceptance not run in this mission slice.

## NEW PUNCH-LIST ITEMS DISCOVERED

- None beyond the known commissioning gates above.

## WARDEN READY

NO — demo slice only; no full target-site regen + cross-site regression + visual check in this mission.
