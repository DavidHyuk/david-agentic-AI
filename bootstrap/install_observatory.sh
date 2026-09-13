#!/usr/bin/env bash
# Author: David Choi (bestshoot21@gmail.com)
# Purpose: stage and start Hermes HQ on loopback and the local Tailscale IP.
set -euo pipefail
OBS_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OBS_HOME="${HERMES_HOME:-$HOME/.hermes}"
OBS_UNITS="$HOME/.config/systemd/user"
OBS_HERMES_CLI="$(command -v hermes)"
OBS_API_ENV="$OBS_HOME/observatory/api.env"
OBS_GATEWAY_DROPIN_DIR="$OBS_UNITS/hermes-gateway.service.d"
OBS_GATEWAY_API_DROPIN="$OBS_GATEWAY_DROPIN_DIR/40-observatory-api.conf"
OBS_CONFIG_BEFORE="missing"
install -d -m 0700 "$OBS_HOME"
exec 9>"$OBS_HOME/.observatory-install.lock"
flock 9
if [[ -f "$OBS_HOME/config.yaml" ]]; then
  OBS_CONFIG_BEFORE="$(sha256sum "$OBS_HOME/config.yaml" | cut -d ' ' -f 1)"
fi
OBS_HOST="${OBSERVATORY_HOST:-$(tailscale status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')}"
OBS_IP="$(tailscale ip -4)"
if [[ ! "$OBS_HOST" =~ ^[a-zA-Z0-9.-]+$ ]]; then
  echo 'Invalid OBSERVATORY_HOST' >&2
  exit 1
fi
if [[ "$OBS_HERMES_CLI" != /* || ! -x "$OBS_HERMES_CLI" ]]; then
  echo 'Hermes CLI must resolve to an executable absolute path' >&2
  exit 1
fi
python3 "$OBS_REPO/bootstrap/stage.py"
python3 "$OBS_REPO/bootstrap/stage_specialist_profiles.py"
if [[ ! -f "$OBS_HOME/kanban/boards/hermes-hq/board.json" ]]; then
  timeout 20s "$OBS_HERMES_CLI" kanban boards create hermes-hq \
    --name 'Hermes HQ Missions' \
    --description 'Goals orchestrated by Hermes HQ across specialist agents.' \
    --icon '✦' --color '#8da47e'
fi
install -d -m 0700 "$OBS_HOME/observatory" "$OBS_HOME/scripts" "$OBS_UNITS" "$OBS_GATEWAY_DROPIN_DIR"
python3 - "$OBS_API_ENV" <<'PY'
import os, pathlib, secrets, sys, tempfile
path = pathlib.Path(sys.argv[1])
try:
    configured = any(line.partition('=')[0].strip() == 'API_SERVER_KEY'
                     and line.partition('=')[2].strip()
                     for line in path.read_text().splitlines())
except OSError:
    configured = False
if not configured:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as handle:
            handle.write('API_SERVER_KEY=' + secrets.token_urlsafe(32) + '\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        pathlib.Path(temporary).replace(path)
    finally:
        pathlib.Path(temporary).unlink(missing_ok=True)
os.chmod(path, 0o600)
PY
OBS_GATEWAY_API_BEFORE="missing"
if [[ -f "$OBS_GATEWAY_API_DROPIN" ]]; then
  OBS_GATEWAY_API_BEFORE="$(sha256sum "$OBS_GATEWAY_API_DROPIN" | cut -d ' ' -f 1)"
fi
cat >"$OBS_GATEWAY_API_DROPIN" <<EOF
# Author: David Choi
# Purpose: loopback Hermes API used only by the private observatory.
[Service]
Environment=API_SERVER_ENABLED=true
Environment=API_SERVER_HOST=127.0.0.1
Environment=API_SERVER_PORT=8642
EnvironmentFile=-$OBS_API_ENV
EOF
OBS_GATEWAY_API_AFTER="$(sha256sum "$OBS_GATEWAY_API_DROPIN" | cut -d ' ' -f 1)"
install -m 0600 "$OBS_REPO/browser/observatory/index.html" "$OBS_REPO/browser/observatory/style.css" "$OBS_REPO/browser/observatory/app.js" "$OBS_HOME/observatory/"
install -m 0600 "$OBS_REPO/browser/observatory/workbench.js" "$OBS_REPO/browser/observatory/workbench.css" "$OBS_HOME/observatory/"
install -m 0700 "$OBS_REPO/scripts/interview_progress.py" "$OBS_REPO/scripts/english_srs.py" "$OBS_HOME/scripts/"
if [[ -d "$OBS_HOME/profiles/english/scripts" ]]; then
  install -m 0700 "$OBS_REPO/scripts/english_srs.py" "$OBS_HOME/profiles/english/scripts/english_srs.py"
fi
install -m 0700 "$OBS_REPO/scripts/observatory.py" "$OBS_HOME/scripts/observatory.py"
python3 - "$OBS_HOME" "$OBS_UNITS" "$OBS_HOST" "$OBS_IP" "$OBS_HERMES_CLI" <<'PY'
import pathlib, sys
home, units, host, tailnet_ip, hermes_cli = sys.argv[1:]
unit = f'''# Author: David Choi
# Purpose: private Hermes observatory on loopback and the Tailscale interface.
[Unit]
Description=Hermes HQ observatory
After=network.target

[Service]
Type=simple
Environment=HERMES_CLI={hermes_cli}
EnvironmentFile=-{home}/observatory/api.env
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
OBS_CONFIG_AFTER="$(sha256sum "$OBS_HOME/config.yaml" | cut -d ' ' -f 1)"
if [[ ( "$OBS_CONFIG_BEFORE" != "$OBS_CONFIG_AFTER" || \
        "$OBS_GATEWAY_API_BEFORE" != "$OBS_GATEWAY_API_AFTER" ) ]] && \
  systemctl --user is-active --quiet hermes-gateway.service; then
  systemctl --user restart hermes-gateway.service
fi
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
