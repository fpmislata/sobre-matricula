import subprocess
import sys
from pathlib import Path


def open_folder(path) -> None:
    p = Path(path)
    if not p.exists():
        return
    if sys.platform == "win32":
        import os
        os.startfile(str(p))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(p)])
    else:
        subprocess.Popen(["xdg-open", str(p)])


def open_file(path) -> None:
    p = Path(path)
    if not p.exists():
        return
    if sys.platform == "win32":
        import os
        os.startfile(str(p))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(p)])
    else:
        subprocess.Popen(["xdg-open", str(p)])