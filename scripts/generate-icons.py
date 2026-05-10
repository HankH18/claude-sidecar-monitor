#!/usr/bin/env python3
"""Generate placeholder PWA icons for the dashboard (pure stdlib).

Run with the system Python: ``/usr/bin/python3 scripts/generate-icons.py``.
Pure-stdlib so no venv needed.
"""

from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

ICON_DIR = Path(__file__).resolve().parent.parent / "packages/dashboard/public/icons"

BG = bytes((11, 14, 20, 255))
FG = bytes((16, 185, 129, 255))
INNER = bytes((11, 14, 20, 255))


def png_bytes(width: int, height: int, raw_rgba: bytes) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    stride = width * 4
    rows = bytearray(height * (stride + 1))
    for y in range(height):
        off = y * (stride + 1)
        rows[off] = 0
        rows[off + 1 : off + 1 + stride] = raw_rgba[y * stride : (y + 1) * stride]
    idat = zlib.compress(bytes(rows), 9)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def render(size: int, *, maskable: bool = False) -> bytes:
    """Build a row-by-row pixel buffer to avoid quadratic Python overhead."""
    cx = (size - 1) / 2
    cy = (size - 1) / 2
    outer_r = size * (0.36 if maskable else 0.42)
    inner_r = outer_r * 0.42
    outer_r2 = outer_r * outer_r
    inner_r2 = inner_r * inner_r

    rows: list[bytes] = []
    for y in range(size):
        dy = y - cy
        dy2 = dy * dy
        row = bytearray(size * 4)
        for x in range(size):
            dx = x - cx
            d2 = dx * dx + dy2
            if d2 <= inner_r2:
                color = INNER
            elif d2 <= outer_r2:
                color = FG
            else:
                color = BG
            row[x * 4 : x * 4 + 4] = color
        rows.append(bytes(row))

    return png_bytes(size, size, b"".join(rows))


def main() -> int:
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    for name, size, maskable in (
        ("icon-192.png", 192, False),
        ("apple-touch-icon-180.png", 180, False),
        ("icon-512.png", 512, False),
        ("icon-512-maskable.png", 512, True),
    ):
        out = ICON_DIR / name
        out.write_bytes(render(size, maskable=maskable))
        print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
