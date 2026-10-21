#!/bin/sh
# Container entrypoint for the Infra bot.
#
# Why this exists: the bot reads its own two vars from the process environment
# (bot/infra/main.py:37 _require_env), but rc_deploy's loader reads *a file* —
# deploy/rc_deploy/config.py:93 calls dotenv_values(deploy/.env) and never looks
# at os.environ. So with a plain `--env-file` run the DO credentials would be
# invisible to the deploy code. This script renders /app/deploy/.env from the
# container environment, normalises the SSH key, then execs the bot.
#
# It is idempotent: it runs on every container start and rewrites the file.
set -eu

DEPLOY_ENV=/app/deploy/.env
SSH_KEY_FILE="${SSH_KEY_FILE:-/run/secrets/ssh_key}"
SSH_KEY_DEST="${HOME:-/home/bot}/.ssh/id_deploy"
STATE_DIR="$(dirname "${INFRA_BOT_STATE_PATH:-/data/infra-state.json}")"

die() {
    echo "entrypoint: $*" >&2
    exit 2
}

# ── 1. required env ────────────────────────────────────────────────
# DO_REGION / DO_SIZE / DO_IMAGE / DNS_TTL have image defaults, so they are not
# listed here. SUBDOMAIN / SECRET_KEY / AGENT_TOKENS / TURN_SECRET are generated
# per deploy by the bot (bot/infra/handlers.py:157) and passed as overrides.
missing=""
for var in TELEGRAM_BOT_TOKEN ALLOWED_TELEGRAM_USER_ID \
           DO_API_TOKEN DO_SSH_KEY_FINGERPRINT DOMAIN GOOGLE_CLIENT_ID; do
    eval "val=\${$var-}"
    [ -n "${val}" ] || missing="${missing} ${var}"
done
if [ -n "${missing}" ]; then
    die "missing required env var(s):${missing}
       Fill them in the env file you pass to the container
       (see bot/infra/.env.example)."
fi

# ── 2. SSH key ─────────────────────────────────────────────────────
# ssh(1) refuses keys that are group/world readable, and bind mounts keep the
# host's mode bits, so always work from a private 0600 copy inside the container.
if [ -f "${SSH_KEY_FILE}" ]; then
    install -m 600 "${SSH_KEY_FILE}" "${SSH_KEY_DEST}"
elif [ -n "${SSH_PRIVATE_KEY_B64-}" ]; then
    umask 077
    printf '%s' "${SSH_PRIVATE_KEY_B64}" | base64 -d > "${SSH_KEY_DEST}"
    chmod 600 "${SSH_KEY_DEST}"
else
    die "no deploy SSH key. Either mount the private key at ${SSH_KEY_FILE}
       (docker-compose.yml does this via the SSH_KEY_HOST_PATH variable),
       or set SSH_PRIVATE_KEY_B64 to its base64 contents."
fi
# The host path from deploy/.env is meaningless in here; point rc_deploy at the copy.
SSH_PRIVATE_KEY="${SSH_KEY_DEST}"

# ── 3. render deploy/.env ──────────────────────────────────────────
# Values must be single-line; python-dotenv reads these back verbatim.
: > "${DEPLOY_ENV}" 2>/dev/null || die "cannot write ${DEPLOY_ENV} (is /app/deploy writable by uid $(id -u)?)"
chmod 600 "${DEPLOY_ENV}"

put() {
    eval "val=\${$1-}"
    [ -n "${val}" ] || return 0
    printf '%s=%s\n' "$1" "${val}" >> "${DEPLOY_ENV}"
}

for var in DO_API_TOKEN DO_REGION DO_SIZE DO_IMAGE DO_SSH_KEY_FINGERPRINT \
           SSH_PRIVATE_KEY DOMAIN SUBDOMAIN DNS_TTL \
           SECRET_KEY AGENT_TOKENS TURN_SECRET TURN_TTL_SECONDS \
           GOOGLE_CLIENT_ID GOOGLE_ALLOWED_EMAILS GOOGLE_ALLOWED_DOMAINS \
           ACCESS_TOKEN_EXPIRE_MINUTES WS_SESSION_TIMEOUT_SECONDS; do
    put "${var}"
done

# load_config() rejects empty values for these even though the bot overrides
# them later; keep harmless placeholders so a half-filled env file still boots.
grep -q '^SUBDOMAIN=' "${DEPLOY_ENV}" || echo 'SUBDOMAIN=rc' >> "${DEPLOY_ENV}"
for k in SECRET_KEY AGENT_TOKENS TURN_SECRET; do
    grep -q "^${k}=" "${DEPLOY_ENV}" || echo "${k}=CHANGE_ME_GENERATED_PER_DEPLOY" >> "${DEPLOY_ENV}"
done

# ── 4. state dir ───────────────────────────────────────────────────
mkdir -p "${STATE_DIR}" 2>/dev/null || true
[ -w "${STATE_DIR}" ] || die "state dir ${STATE_DIR} is not writable by uid $(id -u).
       Recreate the 'infra_state' volume, or chown it to 10001:10001."

echo "entrypoint: ready (domain=${DOMAIN}, state=${INFRA_BOT_STATE_PATH:-/data/infra-state.json})"
exec "$@"
