from pathlib import Path


def has_valid_mbr(image_path: Path) -> bool:
    """Return True if the file at image_path has an MBR boot signature (0x55 0xAA at offset 510).

    Raises:
        ValueError: If image_path does not exist or is not a regular file.
    """
    if not image_path.is_file():
        raise ValueError(f"Not a file: {image_path}")
    with image_path.open("rb") as f:
        f.seek(510)
        sig = f.read(2)
    return sig == b"\x55\xaa"
