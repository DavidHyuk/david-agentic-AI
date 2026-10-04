#!/usr/bin/env bash
# __author__ = 'David Choi (bestshoot21@gmail.com)'
# Purpose: install the standalone Codex retry helper and persistent user service.
set -euo pipefail
RESUME_SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
RESUME_REPO_DIR="$(cd -- "$RESUME_SOURCE_DIR/.." && pwd)"
RESUME_INSTALL_DIR="$HOME/.local/lib/codex-auto-resume"
RESUME_UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$RESUME_INSTALL_DIR" "$RESUME_UNIT_DIR" "$HOME/bin"
if [[ -e "$HOME/bin/codex-auto-resume" && ! -L "$HOME/bin/codex-auto-resume" ]]; then
    cp -p "$HOME/bin/codex-auto-resume" "$RESUME_INSTALL_DIR/original-$(date +%Y%m%dT%H%M%S).sh"
fi
install -m 0755 "$RESUME_REPO_DIR/scripts/codex_auto_resume.py" "$RESUME_INSTALL_DIR/codex_auto_resume.py"
ln -sfn "$RESUME_INSTALL_DIR/codex_auto_resume.py" "$HOME/bin/codex-auto-resume"
install -m 0644 "$RESUME_SOURCE_DIR/codex-auto-resume.service" "$RESUME_UNIT_DIR/codex-auto-resume.service"
systemctl --user daemon-reload
systemctl --user enable --now codex-auto-resume.service
systemctl --user restart codex-auto-resume.service
systemctl --user --no-pager status codex-auto-resume.service
