from typing import Optional

from sqlalchemy import Column, String
from sqlmodel import Field, SQLModel


class HashIndexEntry(SQLModel, table=True):
    """One confirmed hash-index record, mirrored from smart_media_detector's
    hash_index.json (see scripts/ingest_hash_index.py). Storage only, no
    route or service layer reads this table yet. smart_media_detector itself
    stays storage-agnostic; it never imports this model or SQLModel."""

    __tablename__ = "hash_index_entries"

    sha1: str = Field(primary_key=True)
    title: Optional[str] = None
    platform: Optional[str] = Field(default=None, sa_column=Column(String, index=True))
    era: Optional[str] = Field(default=None, sa_column=Column(String, index=True))
    md5: Optional[str] = None
    crc32: Optional[str] = None
