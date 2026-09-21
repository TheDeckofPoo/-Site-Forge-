# MSCATL_CP1 first divergence

**Stage:** PHYSICAL_WORD_RESOLVER / Configio Desc → EIPModules bank join

**Not CP2 cause:** ALL_ZERO EIPModules banks → effective bank derivation

**CP1 cause:** Desc form IB32DATA/OB32PDATA is RTA token, not Rockwell catalog; exact bank==InputBank/OutputBank misses mid-span banks inside DirectSize

**EIPModules bank state:** `ALL_NONZERO_RAW`

**After deterministic rule `rta_32pt_token_direct_bank_span_match`:** ASSIGNED=842 unresolved=0

**Resolver enabled:** True

**AI:** not invoked — deterministic evidence explains the pattern.
