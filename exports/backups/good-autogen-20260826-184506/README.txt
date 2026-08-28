Good autogen backup — 20260826-184506
================================

Source PACK run:
  exports/autogen/20260826-184033-20260813-1132-MSCRENO-MSCRENOPACK-RUN

Contents:
  PACK_20260826-184033/   Full dated PACK export (L5X + maps + reports)
  root_exports/           Root autogen copies (PACK/PICK/SHIP L5X + maps)
  scripts/                fortna_autogen.py + related IO extractors at backup time

Notes from this run:
  - Configio.asc primary bank resolver (Reno empty EIPCSV)
  - OutputBank 0 supported (AENTR3 MX pushers)
  - ENC classified as encoder; MX*SSV as digital_out
  - IO_MAP adapters sorted numerically
  - Report: 922 mapped / 84 unmapped IO points

Restore:
  Copy L5X from PACK_20260826-184033\MSCRENO_MSCRENOPACK.L5X
  Open as NEW project in Studio (File → Open), do not Import into existing .acd
