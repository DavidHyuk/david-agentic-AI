#!/usr/bin/env bash
# Author: David Choi (bestshoot21@gmail.com)
# Purpose: stage and start Hermes HQ on loopback and the local Tailscale IP.
set -euo pipefail
OBS_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OBS_HOME="${HERMES_HOME:-$HOME/.hermes}"
OBS_UNITS="$HOME/.config/systemd/user"
OBS_HOST="${OBSERVATORY_HOST:-$(tailscale status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')}"
OBS_IP="$(tailscale ip -4)"
if [[ ! "$OBS_HOST" =~ ^[a-zA-Z0-9.-]+$ ]]; then
  echo 'Invalid OBSERVATORY_HOST' >&2
  exit 1
fi
install -d -m 0700 "$OBS_HOME/observatory" "$OBS_HOME/scripts" "$OBS_UNITS"
install -m 0600 "$OBS_REPO/browser/observatory/index.html" "$OBS_REPO/browser/observatory/style.css" "$OBS_REPO/browser/observatory/app.js" "$OBS_HOME/observatory/"
install -m 0600 "$OBS_REPO/browser/observatory/workbench.js" "$OBS_REPO/browser/observatory/workbench.css" "$OBS_HOME/observatory/"
install -m 0700 "$OBS_REPO/scripts/interview_progress.py" "$OBS_REPO/scripts/english_srs.py" "$OBS_HOME/scripts/"
if [[ -d "$OBS_HOME/profiles/english/scripts" ]]; then
  install -m 0700 "$OBS_REPO/scripts/english_srs.py" "$OBS_HOME/profiles/english/scripts/english_srs.py"
fi
install -m 0700 "$OBS_REPO/scripts/observatory.py" "$OBS_HOME/scripts/observatory.py"
python3 - "$OBS_HOME" "$OBS_UNITS" "$OBS_HOST" "$OBS_IP" <<'PY'
import pathlib, sys
home, units, host, tailnet_ip = sys.argv[1:]
unit = f'''# Author: David Choi
# Purpose: private Hermes observatory on loopback and the Tailscale interface.
[Unit]
Description=Hermes HQ observatory
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 "{home}/scripts/observatory.py" --home "{home}" --assets "{home}/observatory" --allowed-host {host} --tailnet-ip {tailnet_ip}
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
UMask=0077

[Install]
WantedBy=default.target
'''
pathlib.Path(units, 'hermes-observatory.service').write_text(unit)
PY
systemctl --user daemon-reload
systemctl --user enable --now hermes-observatory.service
systemctl --user restart hermes-observatory.service
python3 - <<'PY'
import time, urllib.request
for attempt in range(50):
    try:
        with urllib.request.urlopen('http://127.0.0.1:8788/api/overview', timeout=3) as response:
            if response.status == 200:
                break
    except OSError:
        time.sleep(0.2)
else:
    raise SystemExit('Observatory failed to start; inspect hermes-observatory.service logs.')
PY
echo "Hermes HQ is running at http://127.0.0.1:8788"
echo "Private tailnet URL: http://$OBS_IP:8788"
echo "Optional HTTPS: sudo tailscale serve --bg --https=8443 http://127.0.0.1:8788"
echo "After enabling HTTPS: https://$OBS_HOST:8443"
