#!/usr/bin/env bash
# Hopline installer for a Linux host running systemd.
# Idempotent: re-running updates the app tree and keeps existing config/state.
set -euo pipefail

APP_DIR=${APP_DIR:-/opt/hopline/app}
CONFIG_DIR=${CONFIG_DIR:-/etc/hopline}
STATE_DIR=${STATE_DIR:-/var/lib/hopline}
BACKUP_DIR=${BACKUP_DIR:-/var/backups/hopline}
SERVICE_USER=${SERVICE_USER:-hopline}
SERVICE_NAME=${SERVICE_NAME:-hopline.service}
UNIT_DIR=${UNIT_DIR:-/etc/systemd/system}
SOURCE_DIR=${SOURCE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}

log() { printf '[hopline-install] %s\n' "$*"; }
die() { printf '[hopline-install] ERROR: %s\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "run as root"
command -v systemctl >/dev/null || die "systemd is required"
[[ -d "$SOURCE_DIR/hopline" ]] || die "source tree not found at $SOURCE_DIR"

if ! command -v sing-box >/dev/null; then
  die "sing-box not found on PATH; install it first (see docs/deployment.md)"
fi

log "source: $SOURCE_DIR"
log "app: $APP_DIR | config: $CONFIG_DIR | state: $STATE_DIR"

# 1. Service account (idempotent)
if ! getent group "$SERVICE_USER" >/dev/null; then
  groupadd --system "$SERVICE_USER"
  log "created group $SERVICE_USER"
fi
if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --gid "$SERVICE_USER" --home-dir "$STATE_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
  log "created user $SERVICE_USER"
fi

install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0700 "$STATE_DIR"
install -d -o root -g root -m 0755 "$(dirname "$APP_DIR")"
install -d -o root -g "$SERVICE_USER" -m 0750 "$CONFIG_DIR"
install -d -o root -g root -m 0700 "$BACKUP_DIR"

# 2. Back up the previous app tree before replacing it
stamp=$(date -u +%Y%m%dT%H%M%SZ)
if [[ -d "$APP_DIR" ]]; then
  backup="$BACKUP_DIR/app-$stamp"
  # Two installs in the same second must not overwrite each other's rollback tree.
  suffix=1
  while [[ -e "$backup" ]]; do
    backup="$BACKUP_DIR/app-$stamp-$suffix"
    suffix=$((suffix + 1))
  done
  cp -a "$APP_DIR" "$backup"
  log "backup: $backup"
fi

# 3. Install application code (tracked files only; never secrets or state)
install -d -o root -g root -m 0755 "$APP_DIR"
if [[ -d "$SOURCE_DIR/hopline" ]]; then
  rm -rf "$APP_DIR/hopline"
  cp -a "$SOURCE_DIR/hopline" "$APP_DIR/hopline"
  find "$APP_DIR/hopline" -name '__pycache__' -type d -prune -exec rm -rf {} +
fi
if [[ -d "$SOURCE_DIR/tools" ]]; then
  rm -rf "$APP_DIR/tools"
  cp -a "$SOURCE_DIR/tools" "$APP_DIR/tools"
  find "$APP_DIR/tools" -name '__pycache__' -type d -prune -exec rm -rf {} +
fi
if [[ -d "$SOURCE_DIR/webui/dist" ]]; then
  rm -rf "$APP_DIR/webui/dist"
  install -d -o root -g root -m 0755 "$APP_DIR/webui"
  cp -a "$SOURCE_DIR/webui/dist" "$APP_DIR/webui/dist"
fi
chown -R root:root "$APP_DIR"
log "app installed to $APP_DIR"

# 4. Config: create from example on first run, never overwrite
if [[ ! -f "$CONFIG_DIR/hopline.toml" ]]; then
  if [[ -f "$SOURCE_DIR/hopline.toml.example" ]]; then
    install -o root -g "$SERVICE_USER" -m 0600 "$SOURCE_DIR/hopline.toml.example" "$CONFIG_DIR/hopline.toml"
    log "config created from example: $CONFIG_DIR/hopline.toml (edit before starting)"
  else
    die "no config at $CONFIG_DIR/hopline.toml and no hopline.toml.example to seed it"
  fi
else
  chown root:"$SERVICE_USER" "$CONFIG_DIR/hopline.toml"
  chmod 0600 "$CONFIG_DIR/hopline.toml"
  log "config preserved: $CONFIG_DIR/hopline.toml"
fi

# 5. systemd unit
install -d -o root -g root -m 0755 "$UNIT_DIR"
install -o root -g root -m 0644 "$SOURCE_DIR/packaging/hopline.service" "$UNIT_DIR/$SERVICE_NAME"
if [[ "$UNIT_DIR" == "/etc/systemd/system" ]]; then
  systemctl daemon-reload
  systemctl enable "$SERVICE_NAME" >/dev/null
  log "service installed and enabled: $SERVICE_NAME"
else
  log "unit written to $UNIT_DIR/$SERVICE_NAME (systemd not touched)"
fi

# 6. Optional restart
if [[ "${HOPLINE_INSTALL_START:-0}" == "1" ]]; then
  systemctl restart "$SERVICE_NAME"
  sleep 2
  systemctl is-active "$SERVICE_NAME" >/dev/null || die "service failed to start; check journalctl -u $SERVICE_NAME"
  log "service restarted and active"
else
  log "skipped restart (set HOPLINE_INSTALL_START=1 to restart automatically)"
fi

log "done"
