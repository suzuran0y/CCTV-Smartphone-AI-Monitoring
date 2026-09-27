
<a id="top"></a>

# CamFlow User Guide

[![Version](https://img.shields.io/badge/version-v1.1.2-black)](https://github.com/suzuran0y/CCTV-Smartphone-AI-Monitoring/issues/2)
[![Android](https://img.shields.io/badge/Android-8.0%2B-green)](CamFlow_UserGuide.md)
[![Role](https://img.shields.io/badge/role-Client-blue)](README.md)
[![Protocol](https://img.shields.io/badge/protocol-HTTP%20Upload-orange)](#sec42)
[![License](https://img.shields.io/badge/license-MIT-lightgrey)](#sec54)

**Language** --- [🇺🇸 English](CamFlow_UserGuide.md) | [🇨🇳 中文](CamFlow_UserGuide_CN.md)

> CamFlow is the Android-side "Image Capture & Transmission" module of the Sentinel system. Installing this application is a prerequisite for deploying and using Sentinel (PC server program + Web Dashboard). This guide is intended to help users understand the application's functionality, reproduce the deployment process, and troubleshoot common issues.

---

## Contents

- [1. Project Overview](#sec1)
  - [1.1. Positioning](#sec11)
  - [1.2. Feature Overview](#sec12)
  - [1.3. Installation](#sec13)

- [2. Usage Workflow](#sec2)
  - [2.1. Launch & Interface](#sec21)
  - [2.2. Connecting to Server](#sec22)
    - [Pairing and credentials](#camera-pairing)
  - [2.3. Settings Page](#sec23)
    - [Resolution preference and measured size](#resolution-preference)
    - [Upload status and diagnostics](#upload-diagnostics)
  - [2.4. Usage Steps](#sec24)

- [3. FAQ](#sec3)
  - [Known upload issue](#known-issues)

- [4. Developer Documentation](#sec4)
  - [4.1. Architecture Overview](#sec41)
  - [4.2. API Reference](#sec42)

- [5. Version Information & Notes](#sec5)
  - [5.1 System Version](#sec51)
  - [5.2 Test Environment](#sec52)
  - [5.3 Roadmap](#sec53)
  - [5.4 Usage & License](#sec54)

---

<a id="sec1"></a>

## 1. Project Overview [⌃](#top)

<a id="sec11"></a>

### 1.1. Positioning [⌃](#top)

The Sentinel system consists of a PC-side server, a Web Dashboard, and an optional AI monitoring module.  
CamFlow acts as the mobile data acquisition client, responsible for capturing real-time camera frames from the smartphone and uploading them to the PC server at a stable and controllable rate. These frames serve as the raw data input for real-time preview, recording, and event analysis.

The project follows a **layered architecture design: Mobile Input → PC Processing & Management**.

In the overall system architecture, the current version of CamFlow is responsible for:

- Camera capture
- JPEG encoding
- Network transmission
- Server discovery & connection state indication
- Runtime mode control (hide preview / stop capture)

All other functionalities — such as video recording, event detection, and AI inference — are handled by the PC-side server.  
This separation reduces complexity on the mobile device and improves maintainability.

CamFlow and the PC server together form the complete Sentinel system:

- **Android Client** — Responsible for image capture and upload  
- **PC Server** — Responsible for video processing, recording, AI analysis, and visualization  

> 📘 For the complete system architecture and deployment instructions, please refer to: **[Sentinel Main System Guide](README.md)**

---

<table>
<tr>
<td width="33%">

#### Engineering Focus

- Distributed video data acquisition architecture  
- Manual LAN server configuration and connection verification
- Lightweight image frame upload protocol  
- Client runtime state management  

</td>

<td width="33%">

#### Intelligent System Focus

- AI monitoring and backend analysis pipeline integration  
- Layered trigger-based visual processing mechanism  
- Mobile device and multimodal model collaboration  
- Real-time vision system performance optimization  

</td>

<td width="33%">

#### This Project Can Serve As:

- An engineering practice example  
- An Android camera integration template  
- A research-oriented vision system prototype  
- A front-end data input module for AI video analysis  

</td>
</tr>
</table>

---

<a id="sec12"></a>

### 1.2. Feature Overview [⌃](#top)

CamFlow provides the following core functionalities:

---

#### 1. Real-time Camera Capture & Transmission

- Capture frames using the Android camera;
- Encode each frame into JPEG format;
- Upload frames to the PC server via HTTP (`/upload` endpoint).

---

#### 2. Server Address Configuration

- Print a copy-ready CamFlow `IP:PORT` when PC-side `server.py` starts;
- Request and save this address on first use, then test the saved address on subsequent launches.

---

#### 3. Connection Testing & Status Visualization

- Display real-time connection status (`Status` / `Server`);
- Provide a **Test connection** button in the Settings page to quickly verify server reachability (typically via `/ping`).

---

#### 4. Runtime Controls & Deployment Flexibility

- **Show debug info**  
  Display runtime debug information (useful for on-site deployment and connection diagnostics).

- **Hide camera preview**  
  Hide the camera preview (black screen) while continuing to upload frames.  
  Useful for privacy-sensitive or discreet deployment scenarios.

- **Stop camera**  
  Stop both camera capture and frame upload.  
  Useful for power saving or temporarily pausing input.

---

<a id="sec13"></a>

### 1.3. Installation [⌃](#top)

Use CamFlow v1.1.2 with Sentinel v1.1.4. Older v1.1.0 / v1.1.1 clients cannot upload to the authenticated server. Review [known issues](#known-issues) before deployment.

#### 1.3.1. Standard User Installation (APK Package)

> Intended for end users / deployment operators.

1. Use the bundled pre-release `CamFlow-v1.1.2.apk` (debug-signed, build 9). If downloading from the project's **Releases** page, check the version and known issues; historical APKs are not compatible with the new server.
2. Install and open CamFlow on your Android device.
3. On first launch, grant camera permission when prompted.

---

#### 1.3.2. Developer / Debug Installation (Android Studio)

> Intended for developers and maintainers.

1. Open the CamFlow project using Android Studio;
2. Connect your Android device and enable USB debugging;
3. Click **Run** to install and launch the app on the device.

---

<a id="sec2"></a>

## 2. Usage Workflow [⌃](#top)

<a id="sec21"></a>

### 2.1. Launch & Interface [⌃](#top)

After opening CamFlow, you will enter the main interface.  
If the server has not yet been connected, the application will typically display a *Not connected* state (see Figure 1).

<table align="center">
  <tr>
    <td align="center">
      <img src="assets/app_main_page.jpg" width="250"><br>
      <b>Figure 1 - Main Interface (Not Connected)</b><br>
    </td>
  </tr>
</table>

---

#### Main Interface Field Explanation

| Field | Possible States | Meaning | Trigger Scenario |
|-------|------------------|---------|------------------|
| **Status** | Not connected | No valid server connection established | First launch / server not configured |
| | Connecting... | Attempting to connect to server | After manual address input |
| | Connected | Successfully connected and verified | `/ping` returned success |
| **Server** | Not connected | No available server address | Not configured / connection failed |
| | xxx.xxx.xxx.xxx(:xxxx) | Saved server IP (and port) | Manual input and successful connection |
| **Mode** | Normal | Capturing and uploading normally with preview shown | Default mode |
| | Hidden Preview | Preview hidden but still uploading | Hide camera preview enabled |
| | Stopped | Capture and upload stopped | Stop camera enabled |
| **Interval** | 120ms | Default sending interval | Default configuration |
| | >120ms | Lower frame rate mode | Interval adjusted (developer option) |

---

<a id="sec22"></a>

### 2.2. Connecting to Server [⌃](#top)

#### 2.2.1. Manual Input

On first launch, CamFlow displays a prompt requesting the Sentinel server address. Start `server.py` on the PC first, then enter the address shown after `CamFlow:` in its startup output.

Prompt explanation and input format:

- **Enter Sentinel server address**
  - Enter the CamFlow address printed by `server.py`.
  - Input the server IP address.
  - If using a non-default port, append the port number.

Format examples:

- `192.168.1.10`  
 (Default port will be automatically appended — typically `8000`.)

- `192.168.1.10:xxxx`  
  (Explicitly specify the port.)

- **Connect**
  - Performs a connection test.
  - If the Dashboard still does not display video after connection:
    - Confirm [pairing](#camera-pairing) is valid and **Ingest** is enabled on the PC Dashboard.
    - Verify firewall and port accessibility.

---

<a id="camera-pairing"></a>

#### 2.2.2. Pairing and Credential Management

1. Ask the administrator to sign into the PC Dashboard and click **Add CamFlow**.
2. In CamFlow Settings, enter the server address, a device name and the 8-character pairing code.
3. Tap **Pair / Re-pair**, then **Save**.
4. The administrator enables **Ingest**; keep the camera running to upload.

Pairing codes are single-use and expire after 5 minutes. Generating a new code replaces the previous one. Keep the administrator token on the PC; never enter it on the phone.

Android Keystore encrypts the upload credential, binds it to the server address and excludes it from backups. **Clear local credentials** removes only the phone's copy. To invalidate it on the server, the administrator must click **Revoke** in Dashboard. Pair again after changing servers, clearing credentials or revocation.

Both default and privacy modes require camera pairing. Default mode permits read-only visitors; privacy mode requires administrator login for viewing. See [Dashboard viewing modes](README.md#privacy-mode). Authentication does not encrypt HTTP: use a trusted LAN or HTTPS. Multiple paired phones still share one stream.

---

<a id="sec23"></a>

### 2.3. Settings Page [⌃](#top)

Tap the **top-right corner** of the main interface to enter the Settings page.
Here you can configure the server address, test connectivity, and control runtime switches.

---

#### 2.3.1. Settings Fields and Controls

| Field | Type | Format | Description |
|-------|------|--------|-------------|
| Server address | Text input | IPv4 or IPv4:Port | Specify the target server address for manual connection |
| Device name | Text input | 1–80 characters | Name shown in Dashboard device management |
| Pairing code | Text input | 8-character code | Single-use code generated by the administrator |
| Upload image quality | Selection | Low / Medium / High | JPEG quality 35 / 55 / 75; higher values generally increase file size |
| Upload rate | Selection | Low / Medium / High | Minimum intervals of 500 / 250 / 120 ms; actual successful FPS depends on capture and upload time |
| Resolution preference | Selection | Low / Medium / High | Camera size preference, not guaranteed dimensions; see [resolution reporting](#resolution-preference) |

---

| Button | Trigger | Result | Description |
|--------|--------|--------|-------------|
| Test connection | Click | Success / Failure | Send a reachability test request to server (typically `/ping`) |
| Save | Click | Save successful | Save current server address and settings |
| Pair / Re-pair | Click | Success / Failure | Exchange a valid code for a device credential; tap Save afterward |
| Clear local credentials | Click | Local credential removed | Does not revoke the server-side credential; see [pairing](#camera-pairing) |

---

| Switch | State | System Behavior | Design Purpose |
|--------|-------|----------------|----------------|
| Show debug info | ON / OFF | Display debug information on main screen | Assist deployment & diagnostics |
| Hide camera preview | ON / OFF | Hide camera preview but continue uploading | Reduce visual exposure / minimize disturbance |
| Stop camera | ON / OFF | Stop capture and upload | Power saving / temporary pause |

> When **Stop camera = ON**, the system will automatically enable *Hide preview* to prevent residual image display.

---

<a id="resolution-preference"></a>

#### 2.3.2. Resolution Preference and Measured Frame Size

Low / Medium / High express a camera resolution preference, not fixed output dimensions. The camera chooses a supported size; different levels may produce the same size. Debug can therefore show:

```text
Resolution preference: Low
Frame size: 480x480
```

Frame size is measured from the current camera crop, which is also used for JPEG encoding. It is not a delivery confirmation. The value updates even while uploads are busy; changing levels clears old dimensions until a fresh frame arrives. No fixed-size resizing, stretching, padding or additional cropping is applied.

<a id="upload-diagnostics"></a>

#### 2.3.3. Upload Status and Diagnostics

Enable **Show debug info** in Settings and return to the camera screen.

| Field / result | Meaning and action |
| --- | --- |
| `OK (200)` / `ok` | Upload accepted; check that successes continue increasing |
| `401/403` | Pairing required, invalid or revoked; obtain a new code and pair again |
| `503` | Administrator needs to enable Ingest |
| `failed` | Failed upload count; inspect its status and network phase |
| `dropped` | Candidate frames skipped while upload slots are busy, not a network packet-loss count |
| `Concurrency` | At most two outstanding uploads; no queued backlog. Arrivals can be out of order |
| `Encode` | JPEG conversion/compression time |
| `Last completed` / `Active` | Completed and active request IDs; do not mix different requests when comparing times |
| `connecting` / `sending image` / `waiting response` | Observed client-side phase, not proof of packet delivery or the root cause |
| `Server processing` | Server-side duration returned in response headers; `unknown` is not zero |

Connect timeout is 3 seconds, read/write timeouts are 4 seconds and the whole-call limit is 5 seconds; failed frames are not automatically replayed. These limits bound waiting but do not fix the underlying failure.

Match a request ID with `upload begin/end` lines in the PC's `log/server.log`. Share only relevant lines, never tokens, authentication databases or full configuration files. If a paired phone still times out with Ingest enabled, see [known issues](#known-issues).

---

<a id="sec24"></a>

### 2.4. Usage Steps [⌃](#top)

#### 2.4.1. Prerequisites

Before using CamFlow, ensure the following conditions are met:

- **Project deployed locally**: The Sentinel repository has been cloned to the PC;
- **Same LAN**: The smartphone and PC server are connected to the same Wi-Fi / LAN;
- **PC server running**: The Sentinel PC-side service is accessible from the phone;
- **Firewall & port allowed**: Default port is `8000` (unless modified). Ensure the PC firewall allows inbound access from the phone.

---

#### 2.4.2. Deployment Workflow

1. Start Sentinel on the PC, save the first-run administrator token and find `CamFlow: <PC_IP>:<PORT>`.
2. Connect the phone and PC to the same trusted LAN; enter that address in CamFlow and test connectivity.
3. Sign into Dashboard as administrator and click **Add CamFlow**.
4. Enter the device name and code in phone Settings; tap **Pair / Re-pair**, then **Save**.
5. The administrator clicks **Enable Ingest**; keep the phone camera running.
6. Check that the phone's `ok` count grows and Dashboard Live View / Last frame age keep updating. Connected alone does not mean upload succeeded.
7. If this fails, use [upload diagnostics](#upload-diagnostics) to inspect pairing, Ingest, request phases and [known issues](#known-issues).

---

<a id="sec3"></a>

## 3. FAQ [⌃](#top)

<a id="known-issues"></a>

**Known issue:** real-device uploads still intermittently time out during connection or response handling, which may leave the web image unchanged for extended periods. The cause is unconfirmed; do not rely on the current build for uninterrupted monitoring. Lower settings do not guarantee recovery. See [upload diagnostics](#upload-diagnostics).


<details>

<summary><strong>Which address should I enter on first use?</strong></summary>

1. Run `python server.py` on the PC.
2. Find `CamFlow: <PC_IP>:8000` in the terminal output.
3. Enter `<PC_IP>:8000` in the app and select **Connect**, or use **Test connection** in Settings first.
4. If it fails, visit `http://<PC_IP>:8000/ping` in the phone browser and check the PC firewall, same-Wi-Fi connection, and AP isolation settings.

</details>

---

<details>

<summary><strong>Test connection failed (/ping unreachable)</strong></summary>

- Clicking **Test connection** in Settings shows failure or no response.

### Possible Causes

1. Incorrect server IP or port;
2. PC server not running or listening on a different port;
3. Firewall blocking incoming connections;
4. Phone not connected to Wi-Fi.

### Troubleshooting Steps

1. Ensure the phone and PC are on the same Wi-Fi network;
2. On the phone browser, visit: `http://<PC_IP>:<PORT>/ping`
- If accessible → TCP connectivity is normal.
- If not accessible → Check firewall, port configuration, or network isolation.

### Solutions

- Correct the IP/port;
- Allow the configured HTTP port (TCP 8000 by default) in the PC firewall.

</details>

---

<details>

<summary><strong>CamFlow shows Connected, but Dashboard has no video</strong></summary>

- Phone status indicates connected;
- PC Dashboard Live View does not update.

### Possible Causes

1. Device pairing is missing/revoked, or privacy mode requires administrator login in the browser.
2. **Ingest** is not enabled on the PC Dashboard (receiving switch is OFF);
3. Upload endpoint path or field name mismatch (e.g., server expects `image` but client sends differently);
4. Upload succeeds but frames are rate-limited or dropped on server side (check logs);
5. Browser cache or page not refreshed.

### Troubleshooting Steps

1. Check whether `/upload` requests are received on the PC server;
2. Refresh the Dashboard page and verify **Ingest** status;
3. Inspect the status code and request phase using [upload diagnostics](#upload-diagnostics). Lower upload settings can reduce load but do not guarantee recovery from the [known timeout issue](#known-issues).

### Solutions

- If pairing is missing or revoked, obtain a new code, tap **Pair / Re-pair**, then **Save**;
- Ensure **Ingest** is enabled;
- Align client/server API contract (path, field name, port);
- Adjust sending interval, resolution, or JPEG quality to match network and PC performance.

</details>

---

<details>

<summary><strong>APK installation blocked or marked unsafe</strong></summary>

- System shows “Installation blocked” or “Unknown source not allowed”.

### Solutions

- Enable installation from unknown sources in system settings;
- Ensure the APK is downloaded from the official GitHub Releases page, not from third-party redistribution.

</details>

---

<a id="sec4"></a>

## 4. Developer Documentation [⌃](#top)

For secondary developers, this section describes CamFlow’s structural position within the Sentinel system, its data flow path, and external contracts (API / protocol), enabling further extension and integration.

---

<a id="sec41"></a>

### 4.1. Architecture Overview [⌃](#top)

```
CamFlow (Android App)
│
├─ [A] UI Layer
│   │
│   ├─ Main Screen
│   │   ├─ Camera Preview (Live preview)
│   │   ├─ Status Header
│   │   │   ├─ Status ∈ {NotConnected, Connecting, Connected}
│   │   │   ├─ Server (Current server address)
│   │   │   ├─ Mode ∈ {Normal, HiddenPreview, Stopped}
│   │   │   └─ Interval (Upload interval in ms)
│   │   │
│   │   └─ Connection Dialog
│   │       └─ First launch / invalid saved address → Manual server input
│   │
│   └─ Settings Screen
│       ├─ Server Address Input
│       ├─ Test Connection (/ping test)
│       ├─ Switches
│       │   ├─ Show Debug Info
│       │   ├─ Hide Camera Preview
│       │   └─ Stop Camera
│       └─ Save (Persist configuration)
│
├─ [B] Application State Layer
│   │
│   ├─ Core State Variables
│   │   ├─ connectionState
│   │   ├─ serverUrl
│   │   ├─ uploadIntervalMs
│   │   └─ flags (debug / previewHidden / cameraStopped)
│   │
│   ├─ State Controller
│   │   ├─ UI ↔ State binding
│   │   ├─ State-driven camera start/stop
│   │   └─ State-driven upload thread control
│   │
│   └─ Thread Model
│       ├─ UI Thread
│       ├─ Camera Callback Thread
│       └─ Network Worker Thread
│
├─ [C] Camera Capture Pipeline
│   │
│   ├─ Permission Management (CAMERA permission)
│   │
│   ├─ Camera Provider (CameraX)
│   │   ├─ Preview UseCase (Display)
│   │   └─ ImageAnalysis UseCase (Frame callback)
│   │
│   └─ Frame Dispatch Strategy
│       ├─ Latest-frame overwrite policy (avoid queue buildup)
│       └─ Frame dropping mechanism (maintain real-time behavior)
│
├─ [D] Encoding & Upload Pipeline
│   │
│   ├─ Frame Encoder
│   │   ├─ YUV → RGB/BGR conversion
│   │   └─ JPEG encoding (adjustable quality)
│   │
│   ├─ Rate Limiter
│   │   └─ Interval-based throttling (uploadIntervalMs)
│   │
│   ├─ HTTP Uploader
│   │   ├─ POST {serverUrl}/upload
│   │   ├─ multipart/form-data
│   │   └─ Response handling (200 / 400 / 503)
│   │
│   └─ Error Handling
│       ├─ Connection failure → Switch to Error state
│       └─ UI feedback update
│
├─ [E] Connectivity Layer
│   │
│   ├─ Manual Address Input
│   │   └─ Support IP or IP:Port format
│   │
│   └─ Connectivity Check
│       └─ GET {serverUrl}/ping → Expect "OK"
│
└─ [F] Persistence Layer
    │
    ├─ SharedPreferences
    │   ├─ Persist serverUrl
    │   ├─ Persist switch states
    │   └─ Persist uploadIntervalMs
    │
    └─ App Startup Restore
        ├─ Restore last configuration on launch
        └─ Auto-reconnect attempt (planned)
```

<a id="sec42"></a>

### 4.2. API Reference [⌃](#top)

#### 4.2.1. Base Contract

- **Base URL**: `http://<PC_IP>:<PORT>`
- **Default Port**: Determined by PC server startup parameters (default: `8000`)
- **Transport Protocol**: HTTP (plaintext; recommended for LAN use only)
- **Client Upload Field Name**: `image`

---

#### 4.2.2. Health Check Endpoint: `GET /ping`

Used by CamFlow Settings page via **Test connection**.

Purpose:
- Distinguish between network connectivity issues and application-level errors.

**Request**

- Method: `GET`
- Path: `/ping`
- Body: None

**Response**

- Status: `200 OK`
- Body: `OK`
- Timeout, connection error, or non-200 status code → considered failure.

**curl Example**

```bash
curl -i "http://<PC_IP>:<PORT>/ping"
```

#### 4.2.3. Frame Upload Endpoint: `POST /upload`

CamFlow continuously uploads image data to the server in the form of **single-frame JPEG images**.

After receiving the request, the server:

- Decodes the image bytes;
- Writes the frame into `FrameBuffer`;
- Makes it available to `/stream` and downstream modules (Recorder / AI Monitor).

---

**Request**

- Method: `POST`
- Path: `/upload`
- Content-Type: `multipart/form-data`
- Authorization: `Bearer <paired-device-token>` (added automatically by CamFlow after pairing; never use the administrator token)

| Field Name | Type | Required | Description |
|------------|------|----------|-------------|
| `image` | JPEG bytes | Yes | A single-frame JPEG image; decoded into an image frame on the server side |

> The `image` field and a valid paired-device credential are required. Missing or invalid credentials return `401/403`; successful `/ping` does not authorize uploads.

---

**Response Format**

- Status: `200 OK`
- Body: `OK`

---

**Common HTTP Status Codes**

| HTTP Status | Body | Meaning |
|-------------|------|---------|
| 503 | `ingest disabled` | Ingest is OFF in the PC Dashboard |
| 400 | `missing image` | `image` field not provided (or incorrect field name) |
| 400 | `decode failed` | Image bytes could not be decoded (corrupted / not JPEG) |
| Network Error | Timeout / connection failed | IP/Port incorrect, firewall issue, different subnet |

---

**curl Example**

```bash
curl -i -X POST "http://<PC_IP>:<PORT>/upload" \
  -F "image=@frame.jpg;type=image/jpeg"
```

---

#### 4.2.4. Video Stream Endpoint: `GET /stream`

> Note: This endpoint is primarily used by the Sentinel Dashboard.
It is typically embedded via: `<img src="/stream">`. CamFlow itself does not actively call this endpoint.

---

**Request**

- Method: `GET`
- Path: `/stream`
- Body: None

**Response Format**

- Content-Type: `multipart/x-mixed-replace; boundary=frame`
- Data Format: Continuous MJPEG frame stream

**curl Example**

```bash
curl -v "http://<PC_IP>:<PORT>/stream"
```
---

#### 4.2.5. Manual Address Configuration

CamFlow does not perform UDP broadcasts or LAN scans in the default workflow. The PC prints a copy-ready address when it starts:

```text
CamFlow:    192.168.1.10:8000    enter this address manually in the app
```

Connection flow:

```text
Run server.py
    → Copy the IP:PORT shown after `CamFlow:`
    → Enter it in the first-launch prompt or Settings
    → Test the connection with GET /ping
    → Save the address
    → Pair with an administrator-generated code
    → Administrator enables Ingest
    → Upload images with POST /upload
```

If the PC's LAN IP changes, CamFlow will detect that the saved address is unavailable on the next launch and prompt for a new address.

---

<a id="sec5"></a>

## 5. Version Information & Notes [⌃](#top)

<a id="sec51"></a>

### 5.1. System Version [⌃](#top)

The Sentinel system consists of the PC-side server program and the Android-side CamFlow application.  
Current version information:

- **CamFlow (Android source) Version**: v1.1.2
- **Bundled APK Version**: v1.1.2 (debug-signed)
- **This Document Version**: v1.1.2
- **Last Updated**: 2026-09-26

---

<a id="sec52"></a>

### 5.2. Test Environment [⌃](#top)

Local validation passed 19 Android unit tests and main/instrumentation APK builds; Android CI also passed. Build 9 completed a basic real-device retest. Keystore instrumentation tests have not run on a device, and sustained/background operation has not completed separate acceptance. The [upload issue](#known-issues) remains unresolved.

The following environments are historical test records, not a complete current-release test matrix:

---

#### Android Side

- OS Version: Android 10 and above  
- Test Device: nova 8 SE Vitality Edition — HarmonyOS 3.0.0  
- Network: Same LAN (Wi-Fi)

---

#### PC Side

- OS: Windows 10 / Windows 11  
- Python Version: Python 3.9+  
- Dependencies: Flask, OpenCV, Requests, etc.  
- Network: Local Area Network (LAN)

> It is not recommended to expose the service directly to the public Internet.  
> Administrator authentication and camera pairing are implemented, but authentication does not encrypt HTTP traffic. Use a trusted LAN or configure HTTPS.

---

<a id="sec53"></a>

## 5.3. Roadmap [⌃](#top)

To improve system completeness and extensibility, future optimizations may include:

- HTTPS deployment and further access controls (administrator authentication and device pairing are implemented)
- WebSocket long connections to replace current HTTP polling (reduce latency and overhead)
- Adaptive frame rate / resolution control (dynamically adjust interval based on network conditions)
- Background execution mode (continue uploading when screen is off)
- Local buffering queue (weak-network tolerance)

---

<a id="sec54"></a>

## 5.4. License & Usage Notice [⌃](#top)

CamFlow is released under the **MIT License**.

Copyright © 2026 Suzuran0y

This project is intended for learning, research, and technical validation purposes.

Before use, please ensure compliance with local laws and regulations, especially regarding image data collection and transmission.

If deploying in real production or commercial environments, it is strongly recommended to improve the security mechanism and performance optimization according to local environment.

---
