#!/usr/bin/env python3
"""Interactive setup for the Peach 1UP owner account.

Creates or overwrites the owner record in the database with a new name and PIN.
Invoked by the FastAPI lifespan on first start (no owner record present).
"""

import getpass
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _get_db_path() -> Path:
    from backend.core.settings import get_db_path
    return get_db_path()


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


def run_setup(db_path: str | Path) -> bool:
    """Create or overwrite the owner account interactively.

    Prompts for name and PIN on stdin. Returns True on success, False if the
    user cancelled (KeyboardInterrupt). Raises on database errors.
    """
    db_path = Path(db_path)
    try:
        name = _prompt_name()
        pin = _prompt_pin()
    except KeyboardInterrupt:
        print("\nAborted.")
        return False

    from backend.core.settings import init_settings
    from backend.service.utils.pin_hashing import hash_pin
    init_settings()  # this script runs standalone, outside the FastAPI lifespan
    pin_hash = hash_pin(pin)

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
            existing.name = name
            existing.pin_hash = pin_hash
            existing.pin_required = True
            existing.can_launch_media = True
            existing.can_edit_environments = True
            existing.can_manage_software = True
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
                can_edit_environments=True,
                can_manage_software=True,
                can_edit_settings=True,
                is_admin=True,
            ))
        db.commit()

    print(f"Owner account '{name}' saved successfully.")
    return True


def main() -> int:
    print("=== Peach 1UP — Owner Account Setup ===")
    try:
        success = run_setup(db_path=_get_db_path())
    except Exception as exc:
        print(f"Error saving owner account: {exc}", file=sys.stderr)
        return 1
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
