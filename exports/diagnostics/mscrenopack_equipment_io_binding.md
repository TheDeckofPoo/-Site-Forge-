# MSCRENOPACK Equipment I/O Binding

Conveyor rows: **1184**

## Motors
- Paired Motor_Starter devices: **79**
- Proven: 79 · Review: 0
- UDT-bound signals: 158

## VFD / MDR (must not be M→P)
- VFD count: 64 · mistaken M→P: **0**
- MDR count: 116 · mistaken M→P: **0**

## Power / Air
- PS_UDT devices: 67
- AirPressure_Switch_UDT: 7
- PS* REVIEW: 0

## P77 acceptance trace
- M77 → `P77.O.Run`
- M77_AUX → `P77.I.Auxiliary_Forward`
- Driven conveyor: **MP106** (not rewritten to P77: True)
- Raw retained: ['M77', 'M77_AUX']

## Safety
ESTOP/MCR/ESR/ESLS remain on ES_UDT.I.ES_OK (no invented MCR/ESR/ESLS UDTs)
