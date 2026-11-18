"""Open a file dialog on the computer running Molt UI."""

from pathlib import Path
import subprocess
import sys
from threading import Lock


_picker_lock = Lock()
_MAC_DIALOG = '''
try
    set selectedFile to choose file with prompt "Choose a file for Molt UI"
    return POSIX path of selectedFile
on error number -128
    return ""
end try
'''
# Tk owns its GUI thread in a separate process, independent of Uvicorn's workers.
_TK_DIALOG = '''
import tkinter as tk
from tkinter.filedialog import askopenfilename
root = tk.Tk()
root.withdraw()
try:
    print(askopenfilename(title="Choose a file for Molt UI"), end="")
finally:
    root.destroy()
'''


def choose_file() -> str | None:
    """Return the original absolute path, or None when the user cancels."""
    if not _picker_lock.acquire(blocking=False):
        raise RuntimeError("A file picker is already open. Select a file or cancel it first.")
    try:
        command = (
            ["/usr/bin/osascript", "-e", _MAC_DIALOG]
            if sys.platform == "darwin"
            else [sys.executable, "-c", _TK_DIALOG]
        )
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("The file picker timed out. Choose File to try again.") from exc
        except OSError as exc:
            raise RuntimeError("Could not open the file picker. Enter the file's absolute path instead.") from exc
        if result.returncode:
            raise RuntimeError(
                "Could not open the file picker. It requires a desktop session on the computer "
                "running Molt UI (and Tkinter on Linux or Windows). Enter the file's absolute path instead."
            )
        # osascript appends one newline; preserve whitespace in the actual path.
        path = result.stdout.removesuffix("\n") if sys.platform == "darwin" else result.stdout
        if not path:
            return None
        selected = Path(path)
        if not selected.is_absolute() or not selected.is_file():
            raise RuntimeError("The selected file is no longer available. Choose another file.")
        return str(selected)
    finally:
        _picker_lock.release()
