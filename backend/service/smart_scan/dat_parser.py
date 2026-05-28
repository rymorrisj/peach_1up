import logging
import xml.etree.ElementTree as ET
from pathlib import Path

logger = logging.getLogger(__name__)


def parse_dat(path: Path) -> list[dict]:
    source = path.stem
    records: list[dict] = []

    try:
        tree = ET.parse(path)
    except ET.ParseError as exc:
        raise ValueError(f"Failed to parse DAT file {path}: {exc}") from exc

    root = tree.getroot()

    # Extract platform hint from <header><name> if present (TOSEC and some Redump DATs)
    platform: str | None = None
    header = root.find("header")
    if header is not None:
        name_el = header.find("name")
        if name_el is not None and name_el.text:
            platform = name_el.text.strip()

    for game in root.iter("game"):
        game_name = game.get("name")
        if not game_name:
            logger.warning("Skipping <game> with no name attribute in %s", path.name)
            continue

        for rom in game.iter("rom"):
            try:
                sha1 = (rom.get("sha1") or "").lower().strip()
                md5 = (rom.get("md5") or "").lower().strip()
                # Redump uses "crc", TOSEC may use "crc" as well
                crc32 = (rom.get("crc") or rom.get("crc32") or "").lower().strip()

                if not sha1 and not md5 and not crc32:
                    logger.warning(
                        "Skipping rom '%s' in game '%s' (%s): no hash fields",
                        rom.get("name", ""),
                        game_name,
                        path.name,
                    )
                    continue

                record: dict = {
                    "title": game_name,
                    "platform": platform,
                    "era": None,
                    "source": source,
                }
                if sha1:
                    record["sha1"] = sha1
                if md5:
                    record["md5"] = md5
                if crc32:
                    record["crc32"] = crc32

                records.append(record)

            except Exception as exc:
                logger.warning(
                    "Skipping malformed rom entry in game '%s' (%s): %s",
                    game_name,
                    path.name,
                    exc,
                )
                continue

    return records
