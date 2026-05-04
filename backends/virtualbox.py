"""VirtualBox backend for Peach 1UP — placeholder."""

from pathlib import Path
from subprocess import Popen
from typing import Tuple

from utils.job_objects import WindowsJobObject


def launch(media_path: Path, era: str, executable_path: str) -> Tuple[Popen, WindowsJobObject]:
    raise NotImplementedError("VirtualBox backend not yet implemented — coming in P2-8")
