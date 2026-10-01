"""Paragraph text of a Hancom .hwp (v5) file.

The Bank of Korea publishes every set of minutes as both PDF and HWP. The PDF text
loses its spaces at every line wrap (Korean lines break inside words), while the
HWP holds the paragraphs and their spacing exactly as typed -- so the HWP is the
source for minutes. Only what is needed is read: the OLE container, the (zlib)
BodyText/Section0 stream, and the paragraph-text records inside it.

Format notes (HWP 5.0 file-format spec): a record header is 32 bits -- tag id
(10 bits), level (10), size (12; 0xFFF means a 32-bit size follows). Tag 67 is
HWPTAG_PARA_TEXT: UTF-16LE text in which code units below 32 are control
characters; the "extended" ones (fields, drawing objects, tables ...) occupy 8
code units, the rest one.
"""

from __future__ import annotations

import io
import struct
import zlib

_PARA_TEXT = 67
_EXTENDED_CONTROLS = {1, 2, 3, 11, 12, 14, 15, 16, 17, 18, 21, 22, 23}


def paragraphs_from_body(body: bytes) -> list[str]:
    """Paragraph texts from a decompressed BodyText section (a sequence of records)."""
    paragraphs: list[str] = []
    pos = 0
    while pos + 4 <= len(body):
        head = struct.unpack("<I", body[pos:pos + 4])[0]
        pos += 4
        tag, size = head & 0x3FF, (head >> 20) & 0xFFF
        if size == 0xFFF:
            size = struct.unpack("<I", body[pos:pos + 4])[0]
            pos += 4
        record = body[pos:pos + size]
        pos += size
        if tag != _PARA_TEXT:
            continue
        text = record.decode("utf-16-le", errors="ignore")
        out: list[str] = []
        i = 0
        while i < len(text):
            code = ord(text[i])
            if code < 32:
                if code in _EXTENDED_CONTROLS:
                    i += 8
                    continue
                if code in (10, 13):
                    out.append("\n")
                elif code == 9:
                    out.append(" ")
            else:
                out.append(text[i])
            i += 1
        paragraphs.append("".join(out).strip())
    return paragraphs


def hwp_paragraphs(data: bytes) -> list[str]:
    import olefile

    ole = olefile.OleFileIO(io.BytesIO(data))
    header = ole.openstream("FileHeader").read()
    if not header.startswith(b"HWP Document File"):
        raise ValueError("not an HWP 5 document")
    flags = struct.unpack("<I", header[36:40])[0]
    if flags & 0x2 or flags & 0x4:
        raise ValueError("encrypted or distribution-only HWP")
    body = ole.openstream("BodyText/Section0").read()
    if flags & 0x1:
        body = zlib.decompress(body, -15)
    return paragraphs_from_body(body)
