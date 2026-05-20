# Alpine image for the Infra bot. Pure-Python deps + minimal OS tools.
#
# Build context MUST be the repo root, since the image bakes in deploy/,
# server/, and web/ — those get rsynced to the droplet at /up time.
#
#   docker build -t rc-infra-bot -f bot/infra/Dockerfile .

FROM python:3.11-alpine

# rc_deploy shells out to these for SSH/SCP/rsync to the droplet.
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

# Secrets (.env files, SSH key) and state are bind-mounted at runtime — never
# baked in. See bot/README.md for the docker run incantation.
WORKDIR /app/bot/infra

# Just start interactive shell
CMD ["/bin/sh"]
