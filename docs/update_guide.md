---
description: How to update the Kuasarr Python app (systemd user service)
---

# Kuasarr Update Guide on Ultra.cc

## Prerequisites
- Python venv at `~/apps/kuasarr/.venv-kuasarr`
- Systemd user service file: `~/.config/systemd/user/kuasarr.service`

## Steps
1. **Stop service**
   ```bash
   systemctl --user stop kuasarr.service
   ```

2. **Update Kuasarr via pip**
   ```bash
   # Use the venv pip to pull the latest version from PyPI:
   ~/apps/kuasarr/.venv-kuasarr/bin/pip install --upgrade kuasarr
   ```

3. **Start service**
   ```bash
   systemctl --user daemon-reload
   systemctl --user start kuasarr.service
   ```

4. **Check status/logs**
   ```bash
   systemctl --user status kuasarr.service
   journalctl --user -u kuasarr.service -f
   ```

## Changing port or internal address
Edit `~/.config/systemd/user/kuasarr.service` (ExecStart line), then:
```bash
systemctl --user daemon-reload
systemctl --user restart kuasarr.service
```

## Troubleshooting
- **“No module named kuasarr” in the service**: Package missing in the service venv. Install with the venv pip, not pyenv-global.
- **Port already in use (OSError 98)**: Stop any manual instance (`pkill -f "python -m kuasarr"`) or change port/address.

## Keep running after logout (host-dependent)
If required and allowed:
```bash
loginctl enable-linger <user-name>
```
