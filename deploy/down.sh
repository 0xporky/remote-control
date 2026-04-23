#!/usr/bin/env bash
# down.sh — destroy the DigitalOcean droplet created by up.sh.
#
# Usage:
#   ./deploy/down.sh             Destroy the droplet tracked in .state.json.
#   ./deploy/down.sh --clear-dns Also delete the A-record.
#   ./deploy/down.sh --help      Show this help.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"
STATE_FILE="$SCRIPT_DIR/.state.json"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
	sed -n '2,7p' "$0" | sed 's/^# \?//'
	exit 0
fi

CLEAR_DNS=false
[[ "${1:-}" == "--clear-dns" ]] && CLEAR_DNS=true

log()  { printf '\033[1;36m[down]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[down]\033[0m %s\n' "$*" >&2; }
err()  { printf '\033[1;31m[down]\033[0m %s\n' "$*" >&2; exit 1; }

command -v doctl >/dev/null || err "doctl not found."
command -v jq    >/dev/null || err "jq not found."

[[ -f "$ENV_FILE" ]]   || err ".env not found at $ENV_FILE."
[[ -f "$STATE_FILE" ]] || { warn "No $STATE_FILE — nothing to tear down."; exit 0; }

# shellcheck disable=SC1090
set -a; source "$ENV_FILE"; set +a
export DIGITALOCEAN_ACCESS_TOKEN="$DO_API_TOKEN"

DROPLET_ID=$(jq -r '.droplet_id // empty' "$STATE_FILE")
DROPLET_IP=$(jq -r '.ip // empty' "$STATE_FILE")
[[ -n "$DROPLET_ID" ]] || err "droplet_id missing from state file."

# ── Graceful stop (best effort, don't block) ──────────────────────────
SSH_KEY="${SSH_PRIVATE_KEY:-$HOME/.ssh/id_ed25519}"
SSH_KEY="${SSH_KEY/#\~/$HOME}"

if [[ -n "$DROPLET_IP" && -f "$SSH_KEY" ]]; then
	log "Attempting graceful docker compose down (10s timeout)..."
	timeout 10 ssh -i "$SSH_KEY" \
		-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
		-o LogLevel=ERROR -o ConnectTimeout=5 \
		"rc@$DROPLET_IP" 'cd app && docker compose down' 2>/dev/null \
		|| warn "Graceful shutdown skipped or failed — proceeding anyway."
fi

# ── Destroy droplet ───────────────────────────────────────────────────
log "Destroying droplet $DROPLET_ID..."
doctl compute droplet delete "$DROPLET_ID" --force >/dev/null
log "Droplet destroyed."

# ── Optional: clear DNS record ────────────────────────────────────────
if $CLEAR_DNS; then
	log "Clearing A-record for $SUBDOMAIN.$DOMAIN..."
	RECORD_ID=$(doctl compute domain records list "$DOMAIN" --output json \
		| jq -r --arg name "$SUBDOMAIN" '.[] | select(.type=="A" and .name==$name) | .id' | head -n1)
	if [[ -n "$RECORD_ID" ]]; then
		doctl compute domain records delete "$DOMAIN" "$RECORD_ID" --force >/dev/null
		log "A-record deleted."
	else
		warn "No A-record found to delete."
	fi
fi

rm -f "$STATE_FILE"
log "State cleared. Compute billing has stopped."
