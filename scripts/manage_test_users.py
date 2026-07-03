#!/usr/bin/env python3
"""Create, remove, or list test sub-accounts for local development.

Not part of the application runtime — a CLI convenience for seeding or
cleaning up throwaway users while exercising the Identity/Session auth model
by hand. Operates directly on the configured database, same as
setup_admin_user.py.
"""

import argparse
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


def _session_factory(db_path: Path):
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

    def _enforce_fk(conn, _rec) -> None:
        conn.cursor().execute("PRAGMA foreign_keys=ON")

    event.listen(engine, "connect", _enforce_fk)
    return sessionmaker(bind=engine)


def create_test_user(name: str, pin: str | None) -> int:
    from backend.core.identity import generate_identity_secret
    from backend.models.user import User
    from backend.service.utils.pin_hashing import hash_pin

    session_factory = _session_factory(_get_db_path())
    with session_factory() as db:
        user = User(
            name=name,
            is_owner=False,
            pin_required=pin is not None,
            pin_hash=hash_pin(pin) if pin else None,
            identity_token_secret=generate_identity_secret(),
            can_launch_media=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"Created test user '{name}' (id={user.id}).")
        return user.id


def remove_test_user(user_id: int) -> bool:
    from backend.models.media_restriction import MediaRestriction
    from backend.models.profile import Profile
    from backend.models.user import User

    session_factory = _session_factory(_get_db_path())
    with session_factory() as db:
        user = db.get(User, user_id)
        if user is None:
            print(f"No user with id={user_id}.", file=sys.stderr)
            return False
        if user.is_owner:
            print("Refusing to remove the owner account.", file=sys.stderr)
            return False

        owner = db.query(User).filter(User.is_owner.is_(True)).first()
        db.query(MediaRestriction).filter(MediaRestriction.user_id == user_id).delete(synchronize_session=False)
        if owner is not None:
            db.query(Profile).filter(Profile.user_id == user_id).update(
                {Profile.user_id: owner.id}, synchronize_session=False
            )
        db.delete(user)
        db.commit()
        print(f"Removed test user id={user_id}.")
        return True


def list_test_users() -> None:
    from backend.models.user import User

    session_factory = _session_factory(_get_db_path())
    with session_factory() as db:
        users = db.query(User).filter(User.is_owner.is_(False)).all()
        if not users:
            print("No non-owner users.")
            return
        for user in users:
            print(f"{user.id}\t{user.name}\tadmin={user.is_admin}\tpin_required={user.pin_required}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    create_p = sub.add_parser("create", help="Create a test sub-account.")
    create_p.add_argument("name")
    create_p.add_argument("--pin", default=None, help="4-6 digit PIN (optional).")

    remove_p = sub.add_parser("remove", help="Remove a test sub-account by id.")
    remove_p.add_argument("user_id", type=int)

    sub.add_parser("list", help="List non-owner users.")

    args = parser.parse_args()

    if args.command == "create":
        create_test_user(args.name, args.pin)
    elif args.command == "remove":
        remove_test_user(args.user_id)
    elif args.command == "list":
        list_test_users()

    return 0


if __name__ == "__main__":
    sys.exit(main())
