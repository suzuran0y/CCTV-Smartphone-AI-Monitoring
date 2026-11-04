# Sentinel Windows 桌面指南

[English](Sentinel_Desktop.md)

## 启动与操作

桌面端适用于安装了 Microsoft Edge WebView2 Evergreen Runtime 的 Windows 10／11。

- **从仓库启动**：安装 Python 3.12 后，双击根目录的 [Sentinel.cmd](../Sentinel.cmd)。首次使用时按提示将桌面依赖安装到项目的 `.venv`。
- **从 Windows x64 目录版启动**：保留整个 `Sentinel` 文件夹（包括 `_internal`），双击 `Sentinel.exe`。

若提示缺少 Runtime，请安装后重新打开 Sentinel。[Microsoft WebView2](https://developer.microsoft.com/microsoft-edge/webview2/)

1. 点击 **Start Sentinel**，等底栏显示 **Running**。首次使用新数据目录时，点击 **Show token** 并保存管理员令牌，再在 Dashboard 的登录区输入。点击 **I saved the token** 可收起令牌提示区。
2. 按 Dashboard 的配对流程连接 CamFlow v1.1.2，手机使用 Dashboard 副标题旁显示的局域网地址。桌面和局域网浏览器共用同一服务和权限规则。
3. 用 **Appearance** 切换 **Default · Light**、**Default · Dark** 或 **Windows XP · Luna Blue**。切换时保持直播、登录及未保存的表单值。桌面配置会在本机保存外观选项。系统标题栏和窗口按钮由 Windows 管理。
4. 点击 **Stop Sentinel**，等待录像完成并释放端口。显示 **Stopped** 后可再次启动。服务运行时关闭窗口会提示确认，取消则继续运行，确认后会完成录像并退出。最小化时服务继续运行。管理员从 Dashboard 关停时，桌面回到 **Stopped**。
5. 管理员可在 **Recordings & Snapshots** 中浏览和下载录像、截图。下载时 WebView2 会提示选择保存位置。停止服务后可选择 **Reset administrator token**，注销现有管理员会话并保留手机配对。

登录后权限面板会自动收起。在可信设备上，可重新展开并点击 **Remember this device for 30 days**，让当前桌面配置在重启后保持登录。点击 **Log out** 可结束该会话。

启动窗口最大为 960 × 780 逻辑像素，并按主屏幕可用空间等比缩小。直播预览随窗口高度缩放。窗口较矮时，接收、录像和截图按钮移到预览上方。窗口较窄时，设置区排列在监控区下方。折叠设置后，**Expand Settings** 会显示在 **Shutdown** 左侧。

## 本地数据与旧部署

桌面端默认把设置、配对记录、日志和录像保存在 `%LOCALAPPDATA%\Sentinel`。

沿用旧部署时先停止旧服务，确认原目录包含 `app\config`，从 PowerShell 或快捷方式传入该项目数据根目录，例如：

```powershell
.\Sentinel.cmd --data-dir "C:\Projects\CCTV-Smartphone-AI-Monitoring"
```

目录版 `Sentinel.exe` 支持同样的参数。指定原数据目录后，可沿用原有配置和摄像头配对。相对 Output Root 以该数据目录为起点，绝对路径仍指向原位置。可用 `--port 8001` 更换端口，或用 `--host 127.0.0.1` 仅允许本机访问。

## 构建 Windows 目录版

打包建议用独立的 Windows x64 Python 3.12 虚拟环境，不继承 Conda 的 NumPy 等全局包：

```powershell
python -m venv .local-validation\desktop-build-env
$buildPython = ".\.local-validation\desktop-build-env\Scripts\python.exe"
& $buildPython -m pip install -r requirements-desktop-build.txt
.\build_desktop.ps1 -Python $buildPython
```

构建完成后，在新生成的 `.local-validation\desktop-build-*\dist\Sentinel\` 目录中打开 `Sentinel.exe`。移动程序时请保留整个文件夹。
