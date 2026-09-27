# NEGATIVE: Cross-panel bank collision

**Forbidden:** Matching Configio Bank=N on panel A to an EIP module with
bank=N on panel B solely because the integers match.

**Required:** Resolve banks only inside the proven panel/adapter ownership
scope. Report `cross_panel_physical_mapping_used: false` for valid claims.
