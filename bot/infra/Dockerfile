# Alpine image for the Infra bot. Pure-Python deps + ssh/rsync for the droplet.
#
# Build context MUST be the repo root, since the image bakes in deploy/,
# server/, and web/ — those get rsynced to the droplet at /up time.
#
#   docker build -t rc-infra-bot -f bot/infra/Dockerfile .
#
# Preferred: use bot/infra/docker-compose.yml, which sets the context, the
# env files and the state volume for you. See bot/infra/RUN_DOCKER.md.

FROM python:3.11-alpine

# rc_deploy shells out to ssh/scp (deploy/rc_deploy/ssh.py) and rsync; the DO
# API and the health probe need CA certificates.
RUN apk add --no-cache openssh-client rsync ca-certificates

WORKDIR /app

# Python deps cached separately from source. bot/infra/requirements.txt chains
# via `-r ../../deploy/requirements.txt`, so both files must be in place before
# pip install.
COPY deploy/requirements.txt /app/deploy/requirements.txt
COPY bot/infra/requirements.txt /app/bot/infra/requirements.txt
RUN pip install --no-cache-dir -r /app/bot/infra/requirements.txt

# Code rsynced to the droplet on /up.
COPY deploy/ /app/deploy/
COPY server/ /app/server/
COPY web/ /app/web/

# The bot itself.
COPY bot/infra/ /app/bot/infra/
COPY bot/infra/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

# Non-root runtime user. /data holds both state files (named volume), /app/deploy
# must be writable because the entrypoint renders deploy/.env into it from the
# container environment, and $HOME/.ssh holds the 0600 copy of the deploy key.
RUN addgroup -g 10001 bot \
    && adduser -D -u 10001 -G bot -h /home/bot bot \
    && mkdir -p /data /home/bot/.ssh \
    && chmod 700 /home/bot/.ssh \
    && chown -R bot:bot /data /home/bot /app/deploy \
    && chmod +x /usr/local/bin/docker-entrypoint.sh

# State lives on the /data volume, not next to the code, so `docker compose up
# --build` can replace the image without losing an in-flight deployment.
#   bot/infra/state.py        -> INFRA_BOT_STATE_PATH
#   deploy/rc_deploy/state.py -> RC_DEPLOY_STATE_PATH
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    INFRA_BOT_STATE_PATH=/data/infra-state.json \
    RC_DEPLOY_STATE_PATH=/data/deploy-state.json \
    SSH_KEY_FILE=/run/secrets/ssh_key \
    DO_REGION=fra1 \
    DO_SIZE=s-1vcpu-1gb \
    DO_IMAGE=ubuntu-24-04-x64 \
    DNS_TTL=60

VOLUME ["/data"]

USER bot
WORKDIR /app/bot/infra

# Secrets (bot token, DO token, SSH key) come from the environment / a mounted
# key at runtime — never baked in. See bot/infra/RUN_DOCKER.md.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD pgrep -f "main.py" >/dev/null || exit 1

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["python", "main.py"]
