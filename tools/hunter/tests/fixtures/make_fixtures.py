"""Regenerate Hunter's SYNTHETIC fixture prints deterministically.

    python -m tools.hunter.tests.fixtures.make_fixtures

Requires reportlab (dev-only).  Output is byte-stable (invariant=1), and the
committed PDFs under prints/ are checked against a regeneration in tests.
All labels are synthetic; no real site or device list is encoded.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRINTS = HERE / "prints"

PAGE = (792, 612)  # landscape letter, points


def _title_block(c, title, sheet, rev):
    c.setLineWidth(1)
    c.rect(500, 30, 280, 110)
    c.setFont("Helvetica", 9)
    c.drawString(510, 115, f"TITLE: {title}")
    c.drawString(510, 90, f"SHEET: {sheet}")
    c.drawString(680, 90, f"REV: {rev}")
    c.drawString(510, 65, "DATE: 2026-09-01")


def _lines(c, x, rows, y0=560, step=28, size=10):
    c.setFont("Helvetica", size)
    y = y0
    for text in rows:
        c.drawString(x, y, text)
        y -= step


def build_set_a(path: Path) -> None:
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=PAGE, invariant=1)
    # page 1 — conveyor / motor / PE / panels / continuation
    _lines(c, 40, [
        "CONVEYOR P1300",
        "MOTOR M1300 DRIVES P1300",
        "VFD1300 FEEDS M1300",
        "PHOTOEYE PE1300 MOUNTED ON P1300",
        "MAIN CONTROL PANEL MCP1",
        "CP2",
        "PLC01 CONTROLLER",
        "NOTE: SEE P-1300 DETAIL",
        "STACK LIGHT SL1300",
    ])
    _lines(c, 420, [
        "SCANNER SCN1600",
        "MRG1400 MERGE",
        "DIV1500 DIVERTER",
        "CS1300 CONTROL STATION",
    ])
    _lines(c, 40, ["CONTINUED ON SHEET E-102"], y0=250)
    _title_block(c, "CONVEYOR POWER", "E-101", "B")
    c.showPage()
    # page 2 — safety devices (labels only; no zone membership may be inferred)
    _lines(c, 40, [
        "EMERGENCY STOP PUSHBUTTON ESPB101",
        "E-STOP 1ES3",
        "PULL CORD ESLS161",
        "ESLS161 IN SAFETY CIRCUIT ESR1",
        "ESR1 SAFETY RELAY",
        "ESR-2A",
        "MASTER CONTROL RELAY MCR1",
        "SAFETY ZONE Z1 BOUNDARY",
        "CONVEYOR P1300",
    ])
    _lines(c, 40, ["FROM SHEET E-101", "SEE SHEET E-999"], y0=260)
    _title_block(c, "SAFETY CIRCUIT", "E-102", "A")
    c.showPage()
    # page 3 — printed I/O
    _lines(c, 40, [
        "REMOTE I/O PANEL RIO1",
        "1734-IB8 SLOT 3",
        "Local:3:I.Data.0 PE1300 PHOTOEYE",
        "Local:3:I.Data.1 ESPB101",
        "TB1-12 -> PE1301",
        "I:1/3 TO PE1302",
        "Local:3:I.Data.2 PE1303 PE1304",
        "RIO1 ADDRESS 10.10.1.20",
    ])
    _title_block(c, "I/O LAYOUT", "E-103", "B")
    c.showPage()
    # page 4 — NO title block; ambiguous / unknown / weak pair
    _lines(c, 40, [
        "S1300 AT END OF LINE",
        "XQ7731 SPARE",
        "M1300 P1300",
        "P1300",
    ])
    c.showPage()
    # page 5 — image only (no text layer)
    from PIL import Image
    from reportlab.lib.utils import ImageReader

    img = Image.new("L", (64, 48), 255)
    for x in range(64):
        for y in range(48):
            if (x * 7 + y * 3) % 11 < 3:
                img.putpixel((x, y), 0)
    c.drawImage(ImageReader(img), 100, 150, width=500, height=375)
    c.rect(40, 40, 712, 532)
    c.showPage()
    c.save()


def build_set_b(path: Path) -> None:
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=PAGE, invariant=1)
    _lines(c, 40, [
        "CONVEYOR P1300",
        "ESR1 SAFETY RELAY",
        "MCP1",
        "CONTINUED ON SHEET E-101",
    ])
    _title_block(c, "PANEL SCHEDULE", "E-201", "C")
    c.showPage()
    c.save()


def build_all(out_dir: Path = PRINTS) -> list:
    out_dir.mkdir(parents=True, exist_ok=True)
    a, b = out_dir / "print_set_a.pdf", out_dir / "print_set_b.pdf"
    build_set_a(a)
    build_set_b(b)
    return [a, b]


if __name__ == "__main__":
    for p in build_all(Path(sys.argv[1]) if len(sys.argv) > 1 else PRINTS):
        print(p)
