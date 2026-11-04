"""Windows entry point. The frozen executable also serves as its own service child."""
import argparse
import ctypes
import os
import sys
import threading
from contextlib import contextmanager
from ctypes.wintypes import HANDLE, RECT
from pathlib import Path

from werkzeug.serving import WSGIRequestHandler, make_server

from app.core.instance_lock import instance_lock
from app.desktop.controller import ServiceController, child_command
from app.desktop.shell import Preferences, create_shell

ROOT = Path(__file__).resolve().parent
ICON = ROOT / "assets/sentinel-camera.ico"


class DesktopRequestHandler(WSGIRequestHandler):
    def log_request(self, code="-", size="-"):
        if self.path == "/control/status" and str(code) == "200":
            return
        super().log_request(code, size)


def has_webview2():
    # Microsoft's documented Evergreen Runtime registration, per machine or per user.
    import winreg
    key = r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for view in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
            try:
                with winreg.OpenKey(hive, key, 0, winreg.KEY_READ | view) as entry:
                    version, _ = winreg.QueryValueEx(entry, "pv")
                    if any(int(part) for part in version.split(".")):
                        return True
            except (OSError, ValueError, AttributeError):
                continue
    return False


@contextmanager
def desktop_host(data_dir, port, host="0.0.0.0"):
    desktop_dir = data_dir / ".sentinel-desktop"
    desktop_dir.mkdir(parents=True, exist_ok=True)
    with instance_lock(desktop_dir / "launcher.lock"):
        app = create_shell(Preferences(desktop_dir / "preferences.json"), port)
        listener = make_server("127.0.0.1", 0, app, threaded=True, request_handler=DesktopRequestHandler)
        controller = ServiceController(child_command(ROOT), data_dir, port, listener.server_port, host=host)
        closing = threading.Event()
        app.config.update(CONTROLLER=controller, CLOSING=closing,
                          SHELL_HOST=f"127.0.0.1:{listener.server_port}")
        thread = threading.Thread(target=listener.serve_forever, name="desktop-shell", daemon=True)
        thread.start()
        try:
            yield app, controller, closing
        finally:
            closing.set()
            controller.stop(final=True)
            controller.finished.wait()
            listener.shutdown()
            listener.server_close()
            thread.join()


def native_message(text, *, confirm=False):
    # MB_DEFBUTTON2 keeps Cancel selected when the user presses Enter inadvertently.
    flags = (0x00000001 | 0x00000020 | 0x00000100) if confirm else 0x00000010
    return ctypes.windll.user32.MessageBoxW(None, text, "Sentinel", flags) == 1


def initial_window_size():
    width, height = 960, 780
    user32 = ctypes.windll.user32
    # Match pywebview's WinForms DPI awareness before reading the system DPI.
    user32.SetProcessDPIAware()
    work_area = RECT()
    if user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(work_area), 0):  # SPI_GETWORKAREA
        scale = (user32.GetDpiForSystem() or 96) / 96
        fit = min(1, ((work_area.right - work_area.left) / scale - 32) / width,
                  ((work_area.bottom - work_area.top) / scale - 32) / height)
        width, height = int(width * fit), int(height * fit)
    return width, height


def window_close_handler(window, controller, closing, confirm=native_message):
    def on_closing():
        if controller.finished.is_set():
            closing.set()
            controller.stop(final=True)
            if controller.finished.is_set():
                return True
        elif closing.is_set():
            return False
        elif not confirm("Sentinel is still running. Stop the service, finalize the recording, and exit?", confirm=True):
            return False
        closing.set()
        controller.stop(final=True)

        def finish():
            controller.finished.wait()
            window.destroy()

        threading.Thread(target=finish, name="desktop-close", daemon=True).start()
        return False
    return on_closing


def run_desktop(argv):
    parser = argparse.ArgumentParser(description="Sentinel Desktop for Windows")
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", choices=("0.0.0.0", "127.0.0.1"), default="0.0.0.0")
    args = parser.parse_args(argv)
    if os.name != "nt":
        parser.error("The desktop launcher requires Windows; use server.py on other platforms.")
    if not 1 <= args.port <= 65535:
        parser.error("invalid service port")
    if not has_webview2():
        native_message("Microsoft Edge WebView2 Runtime is missing. Install the Evergreen Runtime and reopen Sentinel.\n"
                       "https://developer.microsoft.com/microsoft-edge/webview2/")
        return 1
    import webview

    data = (args.data_dir or Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Sentinel").resolve()
    try:
        with desktop_host(data, args.port, args.host) as (app, controller, closing):
            url = f"http://{app.config['SHELL_HOST']}/#{app.config['DESKTOP_KEY']}"
            webview.settings.update(ALLOW_DOWNLOADS=True, ALLOW_FILE_URLS=False,
                                    OPEN_EXTERNAL_LINKS_IN_BROWSER=True)
            width, height = initial_window_size()
            window = webview.create_window("Sentinel Desktop", url=url, width=width, height=height,
                                           min_size=(min(640, width), min(480, height)),
                                           text_select=True, zoomable=True)
            window.events.closing += window_close_handler(window, controller, closing)
            webview.start(gui="edgechromium", private_mode=False,
                          storage_path=str(data / ".sentinel-desktop" / "webview"), icon=str(ICON))
    except (OSError, RuntimeError) as error:
        native_message(str(error))
        return 1
    return 0


def restore_service_pipes():
    # The windowed bootloader leaves Python's stdio unset, even with redirected handles.
    import msvcrt

    get_handle = ctypes.windll.kernel32.GetStdHandle
    get_handle.restype = HANDLE
    sys.stdin = open(msvcrt.open_osfhandle(get_handle(-10), os.O_RDONLY), encoding="utf-8")
    sys.stdout = sys.stderr = open(msvcrt.open_osfhandle(get_handle(-11), os.O_WRONLY), "w",
                                   encoding="utf-8", buffering=1)


def main():
    if sys.argv[1:2] == ["--service"]:
        if sys.stdin is None:
            restore_service_pipes()
        from server import desktop_event, main as service
        try:
            service(sys.argv[2:])
        except (OSError, RuntimeError, ValueError) as error:
            desktop_event("error", message=str(error))
            return 1
        return 0
    if sys.stderr is None:
        sys.stdout = sys.stderr = open(os.devnull, "w", encoding="utf-8")
    return run_desktop(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
