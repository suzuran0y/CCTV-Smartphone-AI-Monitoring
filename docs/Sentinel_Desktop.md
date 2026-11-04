# Sentinel Windows Desktop

[简体中文](Sentinel_Desktop_CN.md)

## Run and operate

Sentinel Desktop runs on Windows 10 or 11 with Microsoft Edge WebView2 Evergreen Runtime.

- **From the repository:** install Python 3.12, then double-click [Sentinel.cmd](../Sentinel.cmd). On first use, accept the prompt to install the desktop dependencies in the project's `.venv`.
- **From the Windows x64 package:** keep the entire `Sentinel` folder, including `_internal`, and double-click `Sentinel.exe`.

If prompted, install the Runtime and reopen Sentinel. [Microsoft WebView2](https://developer.microsoft.com/microsoft-edge/webview2/)

1. Select **Start Sentinel** and wait for **Running**. On first launch with a new data directory, click **Show token**, save the administrator token and enter it in the Dashboard sign-in panel. Click **I saved the token** to dismiss the token panel.
2. Pair CamFlow v1.1.2 as usual and use the address shown next to the Dashboard subtitle. The desktop view and LAN browsers use the same service and access rules.
3. Select **Appearance** to switch between **Default · Light**, **Default · Dark** and **Windows XP · Luna Blue**. The live stream, session and unsaved form values stay intact. The desktop profile saves the appearance locally. Windows supplies the native title bar and window controls.
4. **Stop Sentinel** finalizes recording and releases the port. After it stops, you can start it again. Closing the window while the service is running asks for confirmation. Cancel keeps monitoring. Minimizing keeps the service running. Dashboard administrator shutdown returns the desktop to **Stopped**.
5. Browse media in **Recordings & Snapshots** after administrator sign-in. WebView2 prompts for a download destination. While stopped, **Reset administrator token** revokes administrator sessions while preserving camera pairings.

After sign-in, the access panel closes automatically. On a trusted device, reopen it and select **Remember this device for 30 days** to keep the current desktop profile signed in across restarts. Select **Log out** to end that session.

The window opens at up to 960 × 780 logical pixels and scales proportionally to fit the primary display. The live preview scales with the window height. In shorter windows, Ingest, Recording and Snapshot move above the preview. In narrower windows, settings appear below the monitoring area. After you collapse settings, **Expand Settings** appears next to **Shutdown**.

## Data and existing installations

By default, the desktop app stores settings, pairings, logs and recordings under `%LOCALAPPDATA%\Sentinel`.

To reuse an installation in place, first stop its service and select the existing root containing `app\config`, for example in PowerShell or a shortcut:

```powershell
.\Sentinel.cmd --data-dir "C:\Projects\CCTV-Smartphone-AI-Monitoring"
```

The packaged `Sentinel.exe` accepts the same options. An existing data folder keeps its settings and paired cameras. A relative Output Root is resolved inside that folder, while an absolute path still points to the same location. Use `--port 8001` if you need a different port, or `--host 127.0.0.1` to limit access to the PC.

## Build a Windows package

Build with a separate Windows x64 Python 3.12 virtual environment that does not inherit global Conda packages:

```powershell
python -m venv .local-validation\desktop-build-env
$buildPython = ".\.local-validation\desktop-build-env\Scripts\python.exe"
& $buildPython -m pip install -r requirements-desktop-build.txt
.\build_desktop.ps1 -Python $buildPython
```

Open `Sentinel.exe` from the new `.local-validation\desktop-build-*\dist\Sentinel\` folder. If you move the app, move that entire folder together.
