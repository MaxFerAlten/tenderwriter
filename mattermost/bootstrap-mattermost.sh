#!/bin/sh
set -eu

log() {
  echo "[mattermost-bootstrap] $*"
}

MM_CONTAINER_NAME="${MM_CONTAINER_NAME:-tw-mattermost}"
MM_ADMIN_USER="${MM_ADMIN_USER:-tw-admin}"
MM_ADMIN_EMAIL="${MM_ADMIN_EMAIL:-tw-admin@tenderwriter.local}"
MM_ADMIN_PASS="${MM_ADMIN_PASS:-TW2026Secure!Pass}"
MM_TEAM_NAME="${MM_TEAM_NAME:-tenderwriter}"
MM_TEAM_DISPLAY_NAME="${MM_TEAM_DISPLAY_NAME:-TenderWriter}"
MM_BOOTSTRAP_RETRIES="${MM_BOOTSTRAP_RETRIES:-60}"
MM_BOOTSTRAP_DELAY_SECONDS="${MM_BOOTSTRAP_DELAY_SECONDS:-2}"

wait_for_mattermost() {
  attempt=1
  while [ "$attempt" -le "$MM_BOOTSTRAP_RETRIES" ]; do
    if docker exec "$MM_CONTAINER_NAME" mmctl system status --local >/dev/null 2>&1; then
      log "Mattermost ready in container ${MM_CONTAINER_NAME} (attempt=${attempt})."
      return 0
    fi

    log "Waiting for Mattermost (attempt ${attempt}/${MM_BOOTSTRAP_RETRIES})..."
    sleep "$MM_BOOTSTRAP_DELAY_SECONDS"
    attempt=$((attempt + 1))
  done

  log "ERROR: Mattermost did not become ready in time."
  return 1
}

user_exists() {
  docker exec "$MM_CONTAINER_NAME" mmctl user search "$MM_ADMIN_USER" --json --local 2>/dev/null \
    | grep -q "\"username\": \"$MM_ADMIN_USER\""
}

ensure_admin_user() {
  if user_exists; then
    log "User ${MM_ADMIN_USER} already exists."
  else
    docker exec "$MM_CONTAINER_NAME" mmctl user create \
      --email "$MM_ADMIN_EMAIL" \
      --username "$MM_ADMIN_USER" \
      --password "$MM_ADMIN_PASS" \
      --system-admin \
      --email-verified \
      --local >/dev/null
    log "Created Mattermost admin user ${MM_ADMIN_USER}."
  fi

  docker exec "$MM_CONTAINER_NAME" mmctl user change-password "$MM_ADMIN_USER" --password "$MM_ADMIN_PASS" --local >/dev/null
  docker exec "$MM_CONTAINER_NAME" mmctl roles system-admin "$MM_ADMIN_USER" --local >/dev/null
  log "Ensured password and system admin role for ${MM_ADMIN_USER}."
}

ensure_team() {
  team_json="$(docker exec "$MM_CONTAINER_NAME" mmctl team search "$MM_TEAM_NAME" --json --local 2>/dev/null || true)"
  if printf '%s' "$team_json" | grep -q "\"name\": \"$MM_TEAM_NAME\""; then
    log "Team ${MM_TEAM_NAME} already exists."
  else
    docker exec "$MM_CONTAINER_NAME" mmctl team create \
      --name "$MM_TEAM_NAME" \
      --display-name "$MM_TEAM_DISPLAY_NAME" \
      --local >/dev/null
    log "Created Mattermost team ${MM_TEAM_NAME}."
    team_json="$(docker exec "$MM_CONTAINER_NAME" mmctl team search "$MM_TEAM_NAME" --json --local 2>/dev/null || true)"
  fi

  team_id="$(printf '%s' "$team_json" | sed -n 's/.*"id": "\([^"]*\)".*/\1/p' | head -n 1)"
  if [ -z "$team_id" ]; then
    log "ERROR: Unable to resolve team id for ${MM_TEAM_NAME}."
    return 1
  fi

  docker exec "$MM_CONTAINER_NAME" mmctl team users add "$team_id" "$MM_ADMIN_USER" --local >/dev/null 2>&1 || true
  log "Ensured ${MM_ADMIN_USER} belongs to team ${MM_TEAM_NAME}."
}

wait_for_mattermost
ensure_admin_user
ensure_team

log "Bootstrap completed successfully."
