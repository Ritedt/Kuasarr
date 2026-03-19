---
description: Guide for installing and configuring Kuasarr on Windows via pip
---

# Windows Installation & Configuration Guide

This guide explains how to install Kuasarr on Windows using `pip` and how to configure it for use with Radarr, Sonarr, and JDownloader.

## Prerequisites
- [Python 3.10+](https://www.python.org/downloads/windows/) installed and added to PATH.
- [JDownloader 2](https://jdownloader.org/download/index) installed and connected to MyJDownloader.
- [FlareSolverr](https://github.com/FlareSolverr/FlareSolverr) (optional, but recommended for some sources).

## 1) Installation

Open a PowerShell or CMD window and follow these steps:

```powershell
# Create a folder for Kuasarr
mkdir C:\Kuasarr
cd C:\Kuasarr

# Create and activate a virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install Kuasarr from PyPI
pip install kuasarr
```

## 2) Initial Startup

Start Kuasarr for the first time:

```powershell
kuasarr
```

By default, the WebUI is available at `http://localhost:9999`.

## 3) Configuration

### WebUI Setup
1. Open `http://localhost:9999` in your browser.
2. Go to the **Configuration** section (or the setup wizard on first run).
3. **JDownloader**: Enter your MyJDownloader email and password.
4. **Captcha**: Choose between DeathByCaptcha or 2Captcha and enter your credentials.
5. **FlareSolverr**: If used, enter the URL (e.g., `http://localhost:8191/v1`).

### Port & Address
If you need to change the port or allow external access:
```powershell
kuasarr --port 8080 --internal_address http://192.168.1.50:8080
```

## 4) Autostart (Optional)

To start Kuasarr automatically with Windows, you can create a shortcut in the `Startup` folder:
1. Press `Win + R`, type `shell:startup` and hit Enter.
2. Right-click -> New -> Shortcut.
3. Target: `C:\Kuasarr\venv\Scripts\kuasarr.exe`.
4. (Optional) Add arguments like `--port 9999` to the target.

## 5) Updating Kuasarr

To update to the latest version, run:
```powershell
.\venv\Scripts\Activate.ps1
pip install --upgrade kuasarr
```

## Troubleshooting
- **Execution Policy**: If `Activate.ps1` fails, run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` in PowerShell.
- **Port Blocked**: Ensure port `9999` is not used by another application or allowed in Windows Firewall.
