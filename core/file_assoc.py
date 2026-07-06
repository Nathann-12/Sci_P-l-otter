"""Windows file association for SciPlotter project files (*.sciproj).

Registers a per-user association (HKEY_CURRENT_USER — no admin rights needed)
so double-clicking a .sciproj file launches the app with the file path. Pure
registry writes via winreg; a no-op with a clear message on non-Windows.
"""
from __future__ import annotations

import os
import sys
from typing import Optional, Tuple

EXT = ".sciproj"
PROG_ID = "SciPlotter.Project"
_APP_NAME = "SciPlotter"


def is_windows() -> bool:
    return os.name == "nt"


def launch_command() -> str:
    """The command Windows should run for an opened .sciproj (with "%1").

    Uses the current interpreter (prefer pythonw.exe so no console flashes) +
    the absolute path to main.py.
    """
    exe = sys.executable or "python"
    pyw = exe.replace("python.exe", "pythonw.exe")
    if os.path.isfile(pyw):
        exe = pyw
    main_py = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")
    return f'"{exe}" "{main_py}" "%1"'


def _icon_path() -> Optional[str]:
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "assets", "icons", "app_icon.ico")
    return p if os.path.isfile(p) else None


def register(command: Optional[str] = None, icon: Optional[str] = None) -> Tuple[bool, str]:
    """Register the .sciproj association for the current user.

    Returns (ok, message). Never raises.
    """
    if not is_windows():
        return False, "File association is only supported on Windows"
    import winreg

    cmd = command or launch_command()
    ico = icon or _icon_path()
    classes = r"Software\Classes"
    try:
        # .sciproj → ProgID
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"{classes}\\{EXT}") as k:
            winreg.SetValue(k, "", winreg.REG_SZ, PROG_ID)
        # ProgID description
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"{classes}\\{PROG_ID}") as k:
            winreg.SetValue(k, "", winreg.REG_SZ, f"{_APP_NAME} Project")
        if ico:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                                  f"{classes}\\{PROG_ID}\\DefaultIcon") as k:
                winreg.SetValue(k, "", winreg.REG_SZ, ico)
        # open command
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                              f"{classes}\\{PROG_ID}\\shell\\open\\command") as k:
            winreg.SetValue(k, "", winreg.REG_SZ, cmd)
        _notify_shell()
        return True, f"Associated {EXT} files with SciPlotter"
    except Exception as e:  # pragma: no cover - registry failure is env-specific
        return False, f"Could not register file association: {e}"


def is_registered() -> bool:
    if not is_windows():
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            rf"Software\Classes\{PROG_ID}\shell\open\command") as k:
            val, _ = winreg.QueryValueEx(k, "")
            return bool(val)
    except OSError:
        return False


def unregister() -> Tuple[bool, str]:
    if not is_windows():
        return False, "File association is only supported on Windows"
    import winreg

    def _rm(path):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
        except OSError:
            pass

    for sub in (
        rf"Software\Classes\{PROG_ID}\shell\open\command",
        rf"Software\Classes\{PROG_ID}\shell\open",
        rf"Software\Classes\{PROG_ID}\shell",
        rf"Software\Classes\{PROG_ID}\DefaultIcon",
        rf"Software\Classes\{PROG_ID}",
        rf"Software\Classes\{EXT}",
    ):
        _rm(sub)
    _notify_shell()
    return True, f"Removed {EXT} association"


def _notify_shell() -> None:
    """Tell Explorer the associations changed so the icon/handler refresh."""
    try:
        import ctypes
        SHCNE_ASSOCCHANGED = 0x08000000
        ctypes.windll.shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, 0, None, None)
    except Exception:
        pass
