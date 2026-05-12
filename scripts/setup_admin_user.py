#!/usr/bin/env python3
"""Interactive setup for the Peach 1UP owner account.

Creates or overwrites the owner record in the database with a new name and PIN.
Invoked by the FastAPI lifespan on first start (no owner record present).
"""

import getpass
import os
import re
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _get_db_path() -> Path:
    settings_path = PROJECT_ROOT / "config" / "settings.yaml"
    if settings_path.exists():
        with settings_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if db_path := data.get("DB_PATH"):
            return Path(db_path)
    return PROJECT_ROOT / "database" / "data" / "peach1up.db"


def _prompt_name() -> str:
    while True:
        name = input("Owner name: ").strip()
        if name:
            return name
        print("Name cannot be empty.")


def _prompt_pin() -> str:
    while True:
        pin = getpass.getpass("PIN (4-6 digits): ")
        if not re.fullmatch(r"\d{4,6}", pin):
            print("PIN must be 4-6 digits only.")
            continue
        confirm = getpass.getpass("Confirm PIN: ")
        if pin != confirm:
            print("PINs do not match. Try again.")
            continue
        return pin


def _hash_pin(pin: str) -> tuple[str, str]:
    from argon2.low_level import Type, hash_secret

    salt = os.urandom(16)
    pin_hash = hash_secret(
        secret=pin.encode(),
        salt=salt,
        time_cost=3,
        memory_cost=65536,
        parallelism=4,
        hash_len=32,
        type=Type.ID,
    ).decode()
    return pin_hash, salt.hex()


def main() -> int:
    print("=== Peach 1UP — Owner Account Setup ===")
    try:
        db_path = _get_db_path()
        name = _prompt_name()
        pin = _prompt_pin()
        pin_hash, _ = _hash_pin(pin)
    except KeyboardInterrupt:
        print("\nAborted.")
        return 1

    try:
        from sqlalchemy import create_engine, event
        from sqlalchemy.orm import sessionmaker

        from backend.models.user import User

        engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )

        def _enforce_fk(conn, _rec) -> None:
            conn.cursor().execute("PRAGMA foreign_keys=ON")

        event.listen(engine, "connect", _enforce_fk)
        session_factory = sessionmaker(bind=engine)

        with session_factory() as db:
            existing = db.query(User).filter(User.is_owner.is_(True)).first()
            if existing:
                existing.id = 1
                existing.name = name
                existing.pin_hash = pin_hash
                existing.pin_required = True
                existing.can_launch_media = True
                existing.can_edit_platforms = True
                existing.can_edit_library = True
                existing.can_manage_profiles = True
                existing.can_edit_settings = True
                existing.is_admin = True
                existing.is_locked = False
                existing.failed_pin_attempts = 0
            else:
                db.add(User(
                    id=1,
                    name=name,
                    is_owner=True,
                    pin_hash=pin_hash,
                    pin_required=True,
                    can_launch_media=True,
                    can_edit_platforms=True,
                    can_edit_library=True,
                    can_manage_profiles=True,
                    can_edit_settings=True,
                    is_admin=True,
                ))
            db.commit()

    except Exception as exc:
        print(f"Error saving owner account: {exc}", file=sys.stderr)
        return 1

    print(f"Owner account '{name}' saved successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
