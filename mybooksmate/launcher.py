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


def _run_bootstrap_gui(python_console, get_pip, requirements, marker, needs_pip):
    import tkinter as tk
    from tkinter import ttk

    state = {"ok": False, "error": None}

    root = tk.Tk()
    root.title("My Books Mate")
    root.resizable(False, False)
    width, height = 360, 120
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    root.geometry(f"{width}x{height}+{(screen_w - width) // 2}+{(screen_h - height) // 2}")
    root.protocol("WM_DELETE_WINDOW", lambda: None)

    label = tk.Label(root, text="Первый запуск: подготовка приложения...", wraplength=320, justify="center")
    label.pack(pady=(20, 10))

    progress = ttk.Progressbar(root, mode="indeterminate", length=300)
    progress.pack(pady=5)
    progress.start(12)

    def set_status(text):
        root.after(0, lambda: label.config(text=text))

    def finish(ok, error=None):
        state["ok"] = ok
        state["error"] = error
        root.after(0, root.destroy)

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
    root.mainloop()

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
