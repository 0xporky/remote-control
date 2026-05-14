#!/usr/bin/env bash
# up.sh — provision a DigitalOcean droplet and deploy the remote-control stack.
#
# Usage:
#   ./deploy/up.sh           Provision droplet and deploy.
#   ./deploy/up.sh --help    Show this help.
#
# Requires: doctl, rsync, ssh, jq, curl.
# Reads configuration from deploy/.env.

set -euo pipefail

# ── Locate script + repo root ─────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"
STATE_FILE="$SCRIPT_DIR/.state.json"

# ── Help ──────────────────────────────────────────────────────────────
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
	sed -n '2,11p' "$0" | sed 's/^# \?//'
	exit 0
fi

# ── Logging ───────────────────────────────────────────────────────────
log()  { printf '\033[1;36m[up]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[up]\033[0m %s\n' "$*" >&2; }
err()  { printf '\033[1;31m[up]\033[0m %s\n' "$*" >&2; exit 1; }

# ── Preflight ─────────────────────────────────────────────────────────
command -v doctl >/dev/null || err "doctl not found. Install: https://docs.digitalocean.com/reference/doctl/"
command -v jq    >/dev/null || err "jq not found. Install: brew install jq"
command -v rsync >/dev/null || err "rsync not found."

[[ -f "$ENV_FILE" ]] || err ".env not found at $ENV_FILE. Copy .env.example and fill in values."

# shellcheck disable=SC1090
set -a; source "$ENV_FILE"; set +a

require() {
	local name="$1"
	local val="${!name:-}"
	[[ -n "$val" && "$val" != CHANGE_ME* ]] || err "Required var $name is missing or still a placeholder in $ENV_FILE."
}
for v in DO_API_TOKEN DO_REGION DO_SIZE DO_IMAGE DO_SSH_KEY_FINGERPRINT \
	 DOMAIN SUBDOMAIN SECRET_KEY GOOGLE_CLIENT_ID AGENT_TOKENS; do
	require "$v"
done

FQDN="${SUBDOMAIN}.${DOMAIN}"
SSH_KEY="${SSH_PRIVATE_KEY:-$HOME/.ssh/id_ed25519}"
SSH_KEY="${SSH_KEY/#\~/$HOME}"
[[ -f "$SSH_KEY" ]] || err "SSH private key not found at $SSH_KEY (set SSH_PRIVATE_KEY in .env)."

export DIGITALOCEAN_ACCESS_TOKEN="$DO_API_TOKEN"

# ── Abort if a droplet is already recorded ────────────────────────────
if [[ -f "$STATE_FILE" ]]; then
	EXISTING_ID=$(jq -r '.droplet_id // empty' "$STATE_FILE")
	EXISTING_IP=$(jq -r '.ip // empty' "$STATE_FILE")
	if [[ -n "$EXISTING_ID" ]]; then
		warn "Droplet $EXISTING_ID already tracked in state file (ip=$EXISTING_IP)."
		warn "Run ./deploy/down.sh first, or delete $STATE_FILE if you know it's stale."
		exit 0
	fi
fi

# ── Cleanup trap: drop the firewall if up.sh dies before completing ──
UP_SUCCESS=0
REMOTE_ENV=""
FIREWALL_ID=""
cleanup() {
	[[ -n "$REMOTE_ENV" ]] && rm -f "$REMOTE_ENV"
	if [[ -n "$FIREWALL_ID" && "$UP_SUCCESS" -ne 1 ]]; then
		warn "up.sh failed — deleting orphan firewall $FIREWALL_ID."
		doctl compute firewall delete "$FIREWALL_ID" --force >/dev/null 2>&1 || true
	fi
}
trap cleanup EXIT

# ── Create cloud firewall (22/80/443; 8000 intentionally NOT exposed) ─
FW_NAME="rc-fw-$(date -u +%Y%m%d-%H%M%S)"
log "Creating cloud firewall $FW_NAME (TCP 22/80/443 in, all out)..."

FIREWALL_ID=$(doctl compute firewall create \
	--name "$FW_NAME" \
	--inbound-rules "protocol:tcp,ports:22,address:0.0.0.0/0,address:::/0 protocol:tcp,ports:80,address:0.0.0.0/0,address:::/0 protocol:tcp,ports:443,address:0.0.0.0/0,address:::/0" \
	--outbound-rules "protocol:tcp,ports:all,address:0.0.0.0/0,address:::/0 protocol:udp,ports:all,address:0.0.0.0/0,address:::/0 protocol:icmp,address:0.0.0.0/0,address:::/0" \
	--output json \
	| jq -r '.[0].id')

[[ -n "$FIREWALL_ID" && "$FIREWALL_ID" != "null" ]] || err "Failed to create firewall."
log "Firewall created: id=$FIREWALL_ID"

# ── Provision droplet ─────────────────────────────────────────────────
DROPLET_NAME="rc-$(date -u +%Y%m%d-%H%M%S)"
log "Creating droplet $DROPLET_NAME ($DO_SIZE in $DO_REGION)..."

CREATE_OUT=$(doctl compute droplet create "$DROPLET_NAME" \
	--image "$DO_IMAGE" \
	--size "$DO_SIZE" \
	--region "$DO_REGION" \
	--ssh-keys "$DO_SSH_KEY_FINGERPRINT" \
	--user-data-file "$SCRIPT_DIR/cloud-init.yaml" \
	--wait \
	--output json)

DROPLET_ID=$(echo "$CREATE_OUT" | jq -r '.[0].id')
DROPLET_IP=$(echo "$CREATE_OUT" | jq -r '.[0].networks.v4[] | select(.type=="public") | .ip_address')

[[ -n "$DROPLET_ID" && "$DROPLET_ID" != "null" ]] || err "Failed to parse droplet ID from create response."
[[ -n "$DROPLET_IP" && "$DROPLET_IP" != "null" ]] || err "Failed to parse public IPv4 from create response."

log "Droplet ready: id=$DROPLET_ID ip=$DROPLET_IP"

# ── Attach droplet to firewall ────────────────────────────────────────
log "Attaching droplet to firewall..."
doctl compute firewall add-droplets "$FIREWALL_ID" --droplet-ids "$DROPLET_ID" >/dev/null \
	|| err "Failed to attach droplet $DROPLET_ID to firewall $FIREWALL_ID."

jq -n --arg id "$DROPLET_ID" --arg ip "$DROPLET_IP" --arg name "$DROPLET_NAME" \
	--arg fqdn "$FQDN" --arg fw "$FIREWALL_ID" \
	'{droplet_id: $id, ip: $ip, name: $name, fqdn: $fqdn, firewall_id: $fw}' > "$STATE_FILE"

# ── Update DNS ────────────────────────────────────────────────────────
log "Updating DNS: $FQDN → $DROPLET_IP (TTL ${DNS_TTL:-60})..."

RECORD_ID=$(doctl compute domain records list "$DOMAIN" --output json \
	| jq -r --arg name "$SUBDOMAIN" '.[] | select(.type=="A" and .name==$name) | .id' | head -n1)

if [[ -n "$RECORD_ID" ]]; then
	doctl compute domain records update "$DOMAIN" \
		--record-id "$RECORD_ID" \
		--record-data "$DROPLET_IP" \
		--record-ttl "${DNS_TTL:-60}" >/dev/null
	log "Updated A-record $RECORD_ID."
else
	doctl compute domain records create "$DOMAIN" \
		--record-type A \
		--record-name "$SUBDOMAIN" \
		--record-data "$DROPLET_IP" \
		--record-ttl "${DNS_TTL:-60}" >/dev/null
	log "Created new A-record."
fi

# ── Wait for SSH ──────────────────────────────────────────────────────
SSH_OPTS=(-i "$SSH_KEY" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
	  -o LogLevel=ERROR -o ConnectTimeout=5)
SSH="ssh ${SSH_OPTS[*]} rc@$DROPLET_IP"

log "Waiting for SSH..."
for i in {1..60}; do
	if $SSH true 2>/dev/null; then
		log "SSH is up (after ${i}s)."
		break
	fi
	[[ $i -eq 60 ]] && err "Timed out waiting for SSH."
	sleep 2
done

# ── Wait for cloud-init to finish (Docker installed) ──────────────────
log "Waiting for cloud-init to finish installing Docker..."
for i in {1..120}; do
	if $SSH 'test -f /var/lib/cloud/instance/cloud-init-complete && command -v docker >/dev/null' 2>/dev/null; then
		log "Cloud-init finished (after ${i}s)."
		break
	fi
	[[ $i -eq 120 ]] && err "Timed out waiting for cloud-init."
	sleep 3
done

# ── Ship the stack ────────────────────────────────────────────────────
log "Uploading sources..."
RSYNC_SSH="ssh ${SSH_OPTS[*]}"
$SSH 'mkdir -p ~/app/deploy'

rsync -a --delete -e "$RSYNC_SSH" \
	--exclude node_modules --exclude dist --exclude __pycache__ --exclude '.venv' --exclude 'venv' \
	"$REPO_ROOT/server/" "rc@$DROPLET_IP:~/app/server/"

rsync -a --delete -e "$RSYNC_SSH" \
	--exclude node_modules --exclude dist --exclude __pycache__ \
	"$REPO_ROOT/web/" "rc@$DROPLET_IP:~/app/web/"

rsync -a -e "$RSYNC_SSH" \
	"$SCRIPT_DIR/docker-compose.yml" "$SCRIPT_DIR/Caddyfile" \
	"rc@$DROPLET_IP:~/app/"

# ── Ship .env with FQDN substituted in ────────────────────────────────
REMOTE_ENV=$(mktemp)

# Pass through only the vars docker-compose.yml references. Drop DO_* / SSH_* etc.
{
	echo "FQDN=$FQDN"
	for key in SECRET_KEY AGENT_TOKENS \
		   GOOGLE_CLIENT_ID GOOGLE_ALLOWED_EMAILS GOOGLE_ALLOWED_DOMAINS \
		   ACCESS_TOKEN_EXPIRE_MINUTES WS_SESSION_TIMEOUT_SECONDS; do
		val="${!key:-}"
		printf '%s=%s\n' "$key" "$val"
	done
} > "$REMOTE_ENV"

scp "${SSH_OPTS[@]}" -q "$REMOTE_ENV" "rc@$DROPLET_IP:~/app/.env"
$SSH 'chmod 600 ~/app/.env'

# ── Start the stack ───────────────────────────────────────────────────
log "Building and starting containers (first build takes ~60s)..."
$SSH 'cd ~/app && docker compose up -d --build' || err "docker compose up failed."

# ── Smoke test ────────────────────────────────────────────────────────
log "Waiting for TLS + /api/health (Let's Encrypt issuance takes up to ~30s)..."
HEALTH_URL="https://$FQDN/api/health"
for i in {1..40}; do
	if curl -fsS -o /dev/null "$HEALTH_URL" 2>/dev/null; then
		log "Health check OK."
		break
	fi
	[[ $i -eq 40 ]] && warn "Health check never succeeded at $HEALTH_URL — check 'docker compose logs' on the droplet."
	sleep 3
done

# ── Summary ───────────────────────────────────────────────────────────
cat <<EOF

✓ Deployment complete.

  URL:     https://$FQDN
  Agent:   python agent/main.py --server wss://$FQDN/ws/signaling --token '\$AGENT_TOKEN'
  SSH:     ssh -i $SSH_KEY rc@$DROPLET_IP
  Logs:    ssh -i $SSH_KEY rc@$DROPLET_IP 'cd app && docker compose logs -f'

Spin down with: ./deploy/down.sh
EOF

UP_SUCCESS=1
