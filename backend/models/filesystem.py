from typing import Optional

from sqlmodel import SQLModel


class DriveEntry(SQLModel):
    letter: str
    path: str
    label: str


class DrivesResult(SQLModel):
    drives: list[DriveEntry]


class DirEntry(SQLModel):
    name: str
    path: str


class FileEntry(SQLModel):
    name: str
    path: str
    size_bytes: int


class BrowseResult(SQLModel):
    current_path: Optional[str] = None
    parent_path: Optional[str] = None
    dirs: list[DirEntry]
    files: list[FileEntry]
