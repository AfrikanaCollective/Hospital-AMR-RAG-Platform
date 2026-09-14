"""Build tiny, real, single-page PDFs by hand for offline parser tests.

No PDF-writing library is a project dependency (pypdf is read-only-friendly;
`local-models`/reportlab are not committed for this), so this constructs the
minimal valid PDF object graph directly. Each string in `lines` is placed on
its own line via a separate `Tj` text-showing operator, top to bottom.
"""

from __future__ import annotations

from pathlib import Path


def _pdf_escape(s: str) -> str:
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def make_pdf(lines: list[str], path: str | Path) -> Path:
    ops = []
    y = 750
    for line in lines:
        ops.append(f"BT /F1 12 Tf 72 {y} Td ({_pdf_escape(line)}) Tj ET")
        y -= 20
    content = ("\n".join(ops) + "\n").encode("latin-1")

    objs = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/Resources<</Font<</F1 4 0 R>>>>"
        b"/MediaBox[0 0 612 792]/Contents 5 0 R>>",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
        b"<</Length " + str(len(content)).encode() + b">>stream\n" + content + b"endstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, o in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj".encode() + o + b"endobj\n"
    xref_start = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode()
    out += b"trailer<</Size " + str(len(objs) + 1).encode() + b"/Root 1 0 R>>\n"
    out += b"startxref\n" + str(xref_start).encode() + b"\n%%EOF"

    p = Path(path)
    p.write_bytes(bytes(out))
    return p
