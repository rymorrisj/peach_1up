"""VHD footer builder for 86Box disk images."""

import struct
import time
import uuid


def _build_vhd_footer(size_bytes: int) -> bytes:
    footer = bytearray(512)
    footer[0:8] = b"conectix"
    struct.pack_into(">I", footer, 8, 0x00000002)
    struct.pack_into(">I", footer, 12, 0x00010000)
    struct.pack_into(">Q", footer, 16, 0xFFFFFFFFFFFFFFFF)
    epoch_2000 = 946684800
    struct.pack_into(">I", footer, 24, max(0, int(time.time()) - epoch_2000))
    footer[28:32] = b"pe1u"
    struct.pack_into(">I", footer, 32, 0x00010000)
    footer[36:40] = b"Wi2k"
    struct.pack_into(">Q", footer, 40, size_bytes)
    struct.pack_into(">Q", footer, 48, size_bytes)
    cylinders = size_bytes // (16 * 63 * 512)
    struct.pack_into(">HBB", footer, 56, cylinders, 16, 63)
    struct.pack_into(">I", footer, 60, 0x00000002)
    struct.pack_into(">I", footer, 64, 0)
    footer[68:84] = uuid.uuid4().bytes
    checksum = (~sum(footer)) & 0xFFFFFFFF
    struct.pack_into(">I", footer, 64, checksum)
    return bytes(footer)
