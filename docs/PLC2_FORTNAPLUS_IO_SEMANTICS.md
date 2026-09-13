# PLC2 — FortnaPlus I/O Semantics (Documentation Re-Read)

**Branch:** `feature/plc2-io-truth`  
**Purpose:** Extract authoritative FortnaPlus training relationships **before** changing Site Forge controller-scope or IO_MAP logic.  
**Sources (training corpus under `docs/training/`):**

| ID | Document |
|----|----------|
| ViewIO | `FPC Docs 3/FPC-The-ViewIO-Screen-and-FORTNADT-Table.docx` |
| IOCard | `FPC Documents 1/FPC-IOCard-Interfaces.docx` |
| FastIO | `FPC Documents 1/FPC-FastIO-Configuration.docx` |
| MotorChains | `FPC Documents 1/FPC-Motor-Startup-Chains.docx` |
| FullsJams | `FPC Documents 1/FPC-Fulls-Jams-Fulljams.docx` |
| StartStop | `FPC Docs 3/FPC-StartStopZones.docx` |

**Generation policy reminder:** RUN tables remain the generation source. Finished PLC2 and CP1/CP2/CP3 prints are validation/reference only.

---

## Canonical hop chain (from documentation)

```
Automation Controller (Machine / AC)
  → IOCard row (driver config name)
  → <Machine>-<Config>-eipcfg.xml  (EtherNet/IP adapters + modules)
  → Adapter (targetip, name) + Module (slot, type)
  → Fortna IO word banks (adapter/module consume banks)
  → Configio.Octal_Word  ↔  Conveyor.IO_Address_Word
  → Conveyor.IO_Address_Bit
  → Conveyor.IO_Name (logical point / part)
  → Conveyor.Type / Motor / Drive / Machine_Name
  → Conveyor “P” part / Mtrchain Motor_Chained* (equipment identity)
```

No hop is justified by “P4xx looks like PLC4.” Ownership is AC/machine + word ownership + explicit table links.

---

## 1. FPC-The-ViewIO-Screen-and-FORTNADT-Table

### Table relationships
- **View I/O screen** presents a word×bit matrix of all defined I/O.
- Each cell shows: **owning AC**, **part name**, **description from Conveyor**, ON/OFF, force/invert/disable.
- **FORTNADT** (`RUN/FORTNA/FORTNADT.asc`): one row per IO **word**; columns encode 16-bit masks for Forced_On, Forced_Off, Inverted, Bits_On_Off.
- **flagmnu** flag 101 / OCTAL_MODE controls whether View I/O / Conveyor display words/bits in octal vs decimal (file row offset +2 for header/row0).

### Controller ownership evidence
- View I/O explicitly shows **which AC owns each word**.
- **“Local I/O Only”** button limits the display to parts controlled by **this AC**.
- Implication: ownership is a first-class runtime concept per word — not a naming convention.

### Equipment identity evidence
- Part name + description come from **Conveyor**.
- Bits with no associated part show Part Name **SPARE**.

### I/O word/bit relationships
- Word/bit addressing is the universal key across View I/O, Conveyor, and FORTNADT.
- Octal↔decimal conversion is mandatory when OCTAL_MODE is set (documented example: Word 321₈ bit 15₈ → word 209₁₀ bit 13₁₀).

### Device-to-conveyor relationships
- Conveyor part identity is bound to the word/bit cell when a part is associated.
- Disable / GoNow come from Conveyor_Disable_I_O / Conveyor_Overide_I_O for associated parts.

### Activation semantics
- Force/invert states persist in FORTNADT as configuration, not ephemeral UI.

### Implications for Transportation scope
- Scope for “this AC” must align with **word ownership / Local I/O**, not plant-wide Conveyor inventory.
- SPARE / unassociated bits are not equipment.

### Implications for IO_MAP
- Logical tags should map to the same word/bit identities View I/O would show for this AC.
- Placeholder/unused points exist as physical channels without Conveyor parts (SPARE) — finished PLC maps many to `NO_PointPlaceholder`.

---

## 2. FPC-IOCard-Interfaces

### Table relationships
- **IOCard**: connects FPC to the RTA EtherNet/IP driver (`Name` must match `<Config>` in XML filename).
- **eipcfg XML**: `RUN/FORTNA/<Machine>-<Config>-eipcfg.xml` (example: `CP2-RTA-eipcfg.xml`).
- XML hierarchy: `EthernetIP` → `Adapter` → `Module` (slot 0 = HEADNODE / adapter type; bridged modules in remaining slots).
- Supporting tables: **EIPModules** (wizard output), **KTX_RIO_ADAPTERS** / IO Adapter Status (auto-populated from Adapter `name`).
- Electrical CSV feeds the EIP configuration wizard.

### Controller ownership evidence
- Machine name is on the AC UI and prefixes the eipcfg filename.
- Each AC has a **dedicated IO NIC** and typically a **separate IO network** (same private IP plan reused per AC).
- Adapter `name` must be unique in IO Adapters Status.

### Equipment identity evidence
- Module `name` / `type` / `slot` define hardware identity in the rack.
- Documented example uses adapter name like `1794-AENT-1` with child `1794-IA16` at slot 1.

### I/O word/bit relationships
- Adapters/modules consume **banks** (words) of input/output; sizes depend on family (1794 Flex, 1734 Point, 1756, PowerFlex, etc.).
- Flex 1794: adapter uses banks; modules consume inputs/outputs; bank layout depends on card mix (documented bank totals per module type).
- CSV/EIPCSV associates Fortna words with racks/slots/types (Electrical-prepared).
- Configio / Conveyor words are the Fortna-side addressing that must align with these banks (see FastIO).

### Device-to-conveyor relationships
- IOCard/eipcfg define **physical channels**, not conveyor topology.
- Conveyor table binds logical parts onto those words/bits.

### Activation semantics
- Connection RPI, POINT2POINT/MULTICAST, module keys, and parameters affect online status — not logical mapping identity.
- Slot status bits report module presence/connection health.

### Implications for Transportation scope
- A controller’s local physical IO tree is whatever appears in **that AC’s eipcfg** + owned words — including adapters whose *names* may look like another panel (e.g. finished PLC2 owns `CP3RIO0` hardware while controlling PLC2 logic).

### Implications for IO_MAP
- Mapping must use the **same adapter/module/slot/bank** model as eipcfg + word map.
- Generic generated names (`T_1794_AENT_*`) are acceptable only if RUN lacks finished-style names; eipcfg Adapter `name` is the documented source for adapter identity when present.
- Wrong adapter/slot/bank assignment is a semantic error even if catalog families match.

---

## 3. FPC-FastIO-Configuration

### Table relationships
- **FastIO** table on the **sending** AC.
- Words defined by **Configio.Octal_Word** and **Conveyor.IO_Address_Word**.
- Receiver needs no extra FastIO config (handles like general IO sync).
- Machine table: receiving AC must be online (`Offline = N`).

### Controller ownership evidence
- **“The sending AC must own the word to be sent.”**
- FastIO is point-to-point AC→AC, not a broadcast of all words.
- Purpose: share selected words faster than 1 Hz sync — **not** a substitute for hard-wired safety.

### Equipment identity / word/bit
- Smallest unit = one IO word; contiguous blocks allowed.
- LowWord/HighWord may be octal or decimal per OCTAL_MODE.

### Implications for Transportation scope
- Cross-AC FastIO does **not** make remote conveyors local equipment.
- Shared words remain owned by the sending AC; receivers consume images of those words.

### Implications for IO_MAP
- Only the owning controller should generate physical map rungs for a word.
- Seeing a word on another AC via FastIO/sync must not create duplicate real mappings on the non-owner.

---

## 4. FPC-Motor-Startup-Chains

### Table relationships
- **Mtrchain**: Motor_Name, Motor_Ndx, Motor_Aux, Heater Bit, Motor_Chained1..N, Timer_Name, Stop Zone, ForceAux, etc.
- Links to **Conveyor** parts (motors, aux inputs, display “P” parts, solenoids).
- Links to **Jamzones** Latch Bit (first Motor_Aux often a jam-zone latch / trigger memory bit).
- Timers from timemenu; Refresh Triggers auto-fills Timer_Name / Heater fields.

### Controller ownership evidence
- Chains run on the AC that owns the motor I/O and jam-zone latch configuration.
- Aux contact inputs are physical Conveyor IO points on that AC.

### Equipment identity evidence
- Motor_Name must **exactly match** Motor_Ndx part name.
- Motor_Chained* selects Conveyor “P” parts for display color (example: motor M1000 → display P1000).
- Multiple chained parts may share one hard-wired starter group.

### I/O word/bit relationships
- Motor output and Motor_Aux / Heater Bit are Conveyor IO points (word/bit).
- Aux ON proves contactor engaged before upstream start.

### Device-to-conveyor relationships
- Explicit: motor ↔ P parts via Motor_Chained*.
- Chain order = physical start order (downstream first).

### Activation semantics
- Start when prior Motor_Aux ON and timer complete.
- Heater Debounce → Heater Error if aux fails.
- ForceAux = Y for VM testing (use motor command in place of aux).

### Implications for Transportation scope
- LOCAL conveyors include those **chained display parts** and motors with aux/heater IO on this AC.
- Relationship closure: motor → chained P parts is documented and exact — preferred over name guessing.

### Implications for IO_MAP
- Map motor run outputs and aux/heater inputs as real points when present on owned words.
- Do not invent mappings for chained display-only parts that have no IO word.

---

## 5. FPC-Fulls-Jams-Fulljams

### Table relationships
- **Fullline**: full eyes, full timers, full-clear timers/outputs.
- **Jamcheck**: jam eyes, timers, errors, clear signals, zone links.
- Photoeyes / timers named by convention but **any input may be used**.

### Naming conventions (soft, not ownership)
- PE…`_F` full, PE…`_J` jam, PE…`_JF`/`_FJ` full-jam.
- Timers `tm` / `tmfc` / `tmfj` / `tmfjc` + eye name.

### Activation semantics
- Full: auto restart after clear timer.
- Jam: requires intervention; timer runs only while section commanded to run.
- Full-jam: hybrid; requires Batches activation.

### Implications for Transportation scope
- PE→conveyor association is often numeric (PE230 ↔ P230) but docs warn naming is convention only.
- Prefer explicit table links (Jamcheck sensor, Fullline sensor, Conveyor fields) over digit heuristics.

### Implications for IO_MAP
- Jam/full PEs are discrete inputs on owned words — real mappings when present.
- Direction is input; logical member typically PE clear/status UDT in PLC generation.

---

## 6. FPC-StartStopZones

### Table relationships
- **StartStopZones** ↔ multiple **Jamzones**.
- **Jamzones**: Enable Bit, Latch Bit, Jammed Bit, Zone Owner, Start/Stop timers.
- **Jamcheck** sensors → jam zones.
- **CombinedJamZones** / **CombinedEnableBits**: AND of E-Stop, air, interlock, MCR, etc. into Enable Bit.
- **Mtrchain**: Latch Bit → first Motor_Aux; optional Stop Zone.

### Controller ownership evidence
- “Usually, all the hardware in a start/stop zone is controlled by a **single control panel**.”
- **Jamzones_Zone Owner** + StartOwnerCtl/StopOwnerCtl control which AC may start/stop a zone and whether requests propagate.
- Making Start/Stop unique per node: **do not distribute** that configuration to all nodes.

### Equipment identity / activation
- Latch Bit ON = zone running; OFF = stopped.
- Enable Bit OFF → Not_Enabled (E-Stop/MCR/interlocks).

### Implications for Transportation scope
- Zone owner is strong evidence for which AC’s local equipment set a jam zone’s motors/PEs belong to.
- Cross-AC start messaging does not relocate physical IO ownership.

### Implications for IO_MAP
- E-Stop / MCR / interlock / PB inputs feeding CombinedEnableBits are real discrete inputs on the owning AC.
- Map them when word-owned; they often appear early in finished CP_I (CS Start/Stop, MCR ES_OK).

---

## Cross-document synthesis for PLC2 I/O truth

### Authoritative ownership signals (ordered preference)
1. **Word ownership by this AC** (View I/O / Local I/O; FastIO “sender must own the word”).
2. **eipcfg adapters/modules on this Machine** (IOCard + XML).
3. **Conveyor.Machine_Name** explicit match to this AC.
4. **Configio/Conveyor word** present on this AC’s word map / owned banks.
5. **Mtrchain / Jamzones Zone Owner / StartStop** links tying motors & P parts to this AC’s IO.
6. Soft naming conventions (PE### ↔ P###) only as weak corroboration — never sole evidence.

### Forbidden
- `P1xx → PLC1`, `P2xx → PLC2`, `CP3RIO → PLC3` assumptions.
- Treating plant-wide Conveyor.asc rows as local because they exist.
- Counting `NO_PointPlaceholder` / SPARE as real device mappings.
- Using finished PLC or prints as generation inputs (validation only).

### Transportation presentation (aligned with CP2 prints)
- LOCAL: controlled by this AC’s owned IO / chains / zones.
- EXTERNAL_REFERENCE: boundary conveyor on another drawing/controller (`TO DRAWING CP4/… P-408`) — compact node only.
- Stop traversal at the boundary.

### IO_MAP presentation (aligned with finished style)
- REAL_LOGICAL_POINT: owned word/bit with Conveyor part (non-SPARE) and resolvable module channel.
- UNUSED_PLACEHOLDER: physical channel present on owned module with no part → `NO_PointPlaceholder`.
- Report these populations **separately**.
