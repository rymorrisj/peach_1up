"""FAT16 boot sector / BPB builder."""

import struct

from backend.service.utils.fat.geometry import (
    _BYTES_PER_SECTOR,
    _FAT_COUNT,
    _HEAD_COUNT,
    _RESERVED_SECTORS,
    _ROOT_ENTRY_COUNT,
    _SECTORS_PER_TRACK,
)


def _build_boot_sector(geo: dict) -> bytes:
    sector = bytearray(512)
    ts     = geo["total_sectors"]

    sector[0:3]  = b"\xEB\x58\x90"
    sector[3:11] = b"PEACH1UP"

    struct.pack_into("<H", sector, 11, _BYTES_PER_SECTOR)
    sector[13] = geo["sectors_per_cluster"]
    struct.pack_into("<H", sector, 14, _RESERVED_SECTORS)
    sector[16] = _FAT_COUNT
    struct.pack_into("<H", sector, 17, _ROOT_ENTRY_COUNT)
    struct.pack_into("<H", sector, 19, ts if ts <= 0xFFFF else 0)
    sector[21] = 0xF8
    struct.pack_into("<H", sector, 22, geo["sectors_per_fat"])
    struct.pack_into("<H", sector, 24, _SECTORS_PER_TRACK)
    struct.pack_into("<H", sector, 26, _HEAD_COUNT)
    struct.pack_into("<I", sector, 28, 0)
    struct.pack_into("<I", sector, 32, ts if ts > 0xFFFF else 0)
    sector[36] = 0x80
    sector[37] = 0x00
    sector[38] = 0x29
    struct.pack_into("<I", sector, 39, 0x50454143)
    sector[43:54] = b"PEACH1UP   "
    sector[54:62] = b"FAT16   "
    sector[510]   = 0x55
    sector[511]   = 0xAA

    return bytes(sector)
