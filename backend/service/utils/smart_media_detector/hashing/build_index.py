"""
Usage:
    python -m backend.service.utils.smart_media_detector.hashing.build_index --dats <dir> [--output <path>] [--rebuild]
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from .dat_parser import parse_dat

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

_DEFAULT_OUTPUT = Path(__file__).parent / "hash_index.json"


def _load_existing(output_path: Path) -> dict:
    if not output_path.exists():
        return {}
    with output_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build or update the smart_media_detector hash index from DAT files."
    )
    parser.add_argument(
        "--dats",
        required=True,
        type=Path,
        metavar="DIR",
        help="Directory to walk recursively for *.dat and *.xml files.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_DEFAULT_OUTPUT,
        metavar="PATH",
        help=f"Output path for hash_index.json (default: {_DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Wipe existing index and regenerate from scratch.",
    )
    args = parser.parse_args()

    dats_dir: Path = args.dats
    output_path: Path = args.output

    if not dats_dir.is_dir():
        logger.error("--dats path does not exist or is not a directory: %s", dats_dir)
        sys.exit(1)

    index: dict = {} if args.rebuild else _load_existing(output_path)
    prior_size = len(index)

    dat_files = sorted(
        p for p in dats_dir.rglob("*") if p.suffix.lower() in {".dat", ".xml"}
    )

    if not dat_files:
        logger.warning("No .dat or .xml files found under %s", dats_dir)

    files_parsed = 0
    entries_added = 0

    for dat_path in dat_files:
        try:
            records = parse_dat(dat_path)
        except Exception as exc:
            logger.error("Failed to parse %s: %s", dat_path.name, exc)
            continue

        files_parsed += 1
        for record in records:
            sha1 = record.get("sha1")
            if not sha1:
                continue
            if sha1 not in index:
                index[sha1] = {
                    "title": record.get("title"),
                    "platform": record.get("platform"),
                    "era": record.get("era"),
                    "source": record.get("source"),
                    "md5": record.get("md5"),
                    "crc32": record.get("crc32"),
                }
                entries_added += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(index, fh, indent=2, ensure_ascii=False)

    print(f"Files parsed:    {files_parsed}")
    print(f"Entries added:   {entries_added}")
    print(f"Total index size: {len(index)} (was {prior_size})")
    print(f"Written to:      {output_path}")


if __name__ == "__main__":
    main()
