import ctypes
from ctypes import wintypes
import os
import subprocess
import sys
import threading


def main():
    if getattr(sys, "frozen", False):
        base_dir = os.path.dirname(os.path.abspath(sys.executable))
    else:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    embed_dir = os.path.join(base_dir, "python-embed")
    python = os.path.join(embed_dir, "pythonw.exe")
    python_console = os.path.join(embed_dir, "python.exe")
    get_pip = os.path.join(embed_dir, "get-pip.py")
    entry_script = os.path.join(base_dir, "mybooksmate", "main.py")
    requirements = os.path.join(base_dir, "requirements.txt")
    marker = os.path.join(embed_dir, ".requirements_installed")

    if not os.path.isfile(python_console):
        _show_error(f"Не найден встроенный интерпретатор Python: {python_console}")
        return
    if not os.path.isfile(entry_script):
        _show_error(f"Не найден mybooksmate/main.py: {entry_script}")
        return

    needs_pip = not _has_pip(python_console)
    needs_requirements = os.path.isfile(requirements) and (
        not os.path.isfile(marker) or os.path.getmtime(marker) < os.path.getmtime(requirements)
    )

    if needs_pip or needs_requirements:
        ok = _run_bootstrap_gui(python_console, get_pip, requirements, marker, needs_pip)
        if not ok:
            return

    if not os.path.isfile(python):
        _show_error(f"Не найден pythonw.exe: {python}")
        return

    subprocess.Popen([python, "-m", "mybooksmate.main"], cwd=base_dir)


def _has_pip(python_console):
    try:
        result = subprocess.run(
            [python_console, "-m", "pip", "--version"],
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return result.returncode == 0
    except OSError:
        return False


# Minimal Win32 (ctypes) bootstrap window instead of tkinter: PyInstaller-frozen
# builds on Python 3.14 fail to bundle Tcl/Tk, because Python 3.14's Tcl 9
# reports its library directory as a zipfs path (e.g. "//zipfs:/lib/tcl/tcl_library")
# rather than a real directory, and PyInstaller silently collects zero Tcl/Tk data
# files for it — the frozen exe then crashes on launch with
# "FileNotFoundError: Tcl data directory ... not found". Avoiding tkinter here
# sidesteps that incompatibility entirely.
_WM_CLOSE = 0x0010
_WM_DESTROY = 0x0002
_WS_CAPTION = 0x00C00000
_WS_SYSMENU = 0x00080000
_WS_VISIBLE = 0x10000000
_WS_CHILD = 0x40000000
_SS_CENTER = 0x00000001
_WS_EX_TOPMOST = 0x00000008
_COLOR_WINDOW = 5
_IDC_ARROW = 32512

# LRESULT/WNDPROC are pointer-sized (64-bit on x64); without explicit argtypes/restype,
# ctypes guesses a 32-bit int for plain Python int arguments and raises OverflowError for
# hwnd/wparam/lparam values that don't fit, so every Win32 call below declares its types.
_LRESULT = ctypes.c_ssize_t
_WNDPROC = ctypes.WINFUNCTYPE(_LRESULT, wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM)

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

_user32.DefWindowProcW.argtypes = [wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM]
_user32.DefWindowProcW.restype = _LRESULT
_user32.PostQuitMessage.argtypes = [ctypes.c_int]
_user32.PostQuitMessage.restype = None
_user32.RegisterClassW.argtypes = [ctypes.c_void_p]
_user32.RegisterClassW.restype = wintypes.ATOM
_user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HANDLE, wintypes.HANDLE, ctypes.c_void_p,
]
_user32.CreateWindowExW.restype = wintypes.HWND
_user32.DestroyWindow.argtypes = [wintypes.HWND]
_user32.DestroyWindow.restype = wintypes.BOOL
_user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HANDLE]
_user32.UnregisterClassW.restype = wintypes.BOOL
_user32.SetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
_user32.SetWindowTextW.restype = wintypes.BOOL
_user32.PeekMessageW.argtypes = [ctypes.c_void_p, wintypes.HWND, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint]
_user32.PeekMessageW.restype = wintypes.BOOL
_user32.TranslateMessage.argtypes = [ctypes.c_void_p]
_user32.TranslateMessage.restype = wintypes.BOOL
_user32.DispatchMessageW.argtypes = [ctypes.c_void_p]
_user32.DispatchMessageW.restype = _LRESULT
_user32.LoadCursorW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR]
_user32.LoadCursorW.restype = wintypes.HANDLE
_user32.GetSystemMetrics.argtypes = [ctypes.c_int]
_user32.GetSystemMetrics.restype = ctypes.c_int
_kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
_kernel32.GetModuleHandleW.restype = wintypes.HANDLE


def _wnd_proc(hwnd, msg, wparam, lparam):
    if msg == _WM_CLOSE:
        return 0  # ignore user attempts to close the window mid-install
    if msg == _WM_DESTROY:
        _user32.PostQuitMessage(0)
        return 0
    return _user32.DefWindowProcW(hwnd, msg, wparam, lparam)


class _WNDCLASS(ctypes.Structure):
    _fields_ = [
        ("style", ctypes.c_uint),
        ("lpfnWndProc", _WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HANDLE),
        ("hIcon", wintypes.HANDLE),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HANDLE),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


def _run_bootstrap_gui(python_console, get_pip, requirements, marker, needs_pip):
    user32 = _user32
    kernel32 = _kernel32

    hinstance = kernel32.GetModuleHandleW(None)
    wndproc = _WNDPROC(_wnd_proc)

    wc = _WNDCLASS()
    wc.style = 0
    wc.lpfnWndProc = wndproc
    wc.hInstance = hinstance
    wc.hCursor = user32.LoadCursorW(None, ctypes.cast(_IDC_ARROW, wintypes.LPCWSTR))
    wc.hbrBackground = _COLOR_WINDOW + 1
    wc.lpszClassName = "MyBooksMateBootstrap"
    user32.RegisterClassW(ctypes.byref(wc))

    width, height = 360, 110
    screen_w = user32.GetSystemMetrics(0)
    screen_h = user32.GetSystemMetrics(1)
    x = (screen_w - width) // 2
    y = (screen_h - height) // 2

    hwnd = user32.CreateWindowExW(
        _WS_EX_TOPMOST,
        wc.lpszClassName, "My Books Mate",
        _WS_CAPTION | _WS_SYSMENU | _WS_VISIBLE,
        x, y, width, height,
        None, None, hinstance, None,
    )
    label_hwnd = user32.CreateWindowExW(
        0, "STATIC", "Первый запуск: подготовка приложения...",
        _WS_CHILD | _WS_VISIBLE | _SS_CENTER,
        10, 15, width - 40, 60,
        hwnd, None, hinstance, None,
    )

    state = {"ok": False, "error": None}
    done = threading.Event()

    def set_status(text):
        user32.SetWindowTextW(label_hwnd, text)

    def finish(ok, error=None):
        state["ok"] = ok
        state["error"] = error
        done.set()

    def worker():
        try:
            if needs_pip:
                set_status("Устанавливается pip...")
                _run_step([python_console, get_pip, "--no-warn-script-location", "--quiet"])

            if os.path.isfile(requirements):
                set_status("Устанавливаются зависимости (это может занять несколько минут)...")
                _run_step([python_console, "-m", "pip", "install", "-r", requirements, "--quiet"])
                with open(marker, "w", encoding="utf-8") as file:
                    file.write("")

            finish(True)
        except subprocess.CalledProcessError as exc:
            finish(False, str(exc))
        except OSError as exc:
            finish(False, str(exc))

    threading.Thread(target=worker, daemon=True).start()

    msg = wintypes.MSG()
    while not done.is_set():
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        done.wait(0.02)

    user32.DestroyWindow(hwnd)
    user32.UnregisterClassW(wc.lpszClassName, hinstance)

    if not state["ok"]:
        _show_error(f"Не удалось подготовить приложение: {state['error']}")
        return False
    return True


def _run_step(args):
    subprocess.run(args, check=True, creationflags=subprocess.CREATE_NO_WINDOW)


def _show_error(message):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, message, "My Books Mate", 0x10)
    except Exception:
        print(message)


if __name__ == "__main__":
    main()
