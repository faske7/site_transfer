"""Generate original simple ST monitor mark as a PNG using stdlib."""
import struct
import zlib
from pathlib import Path

size = 512
rows = []
for y in range(size):
    row = bytearray([0])
    for x in range(size):
        color = (16, 23, 34, 255)
        if 75 <= x < 437 and 100 <= y < 340:
            color = (126, 187, 245, 255)
        if 90 <= x < 422 and 115 <= y < 325:
            color = (32, 49, 69, 255)
        if (120 <= x < 392 and 150 <= y < 170) or (120 <= x < 260 and 195 <= y < 211) or (120 <= x < 330 and 235 <= y < 251):
            color = (126, 187, 245, 255)
        if (240 <= x < 272 and 340 <= y < 390) or (170 <= x < 342 and 390 <= y < 405):
            color = (126, 187, 245, 255)
        row.extend(color)
    rows.append(row)
def chunk(name, data):
    return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name + data) & 0xffffffff)
dest = Path("src-tauri/icons/source.png")
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size,size,8,6,0,0,0)) + chunk(b"IDAT",zlib.compress(b"".join(rows))) + chunk(b"IEND",b""))
