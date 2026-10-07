# Running the Infra bot in one container

The Infra bot is the only piece of this project that has to run 24/7 on a Linux
host: it waits for `/up` in Telegram, provisions the DigitalOcean droplet, and
tears it down on `/down`. Everything it needs is baked into one image.

What the container does **not** do: run the desktop agent (that's `bot/agent/`
on Windows) and it does not host the server/web app (those run on the droplet).

## 0. Prerequisites

- Docker with the Compose plugin (`docker compose version`).
- A BotFather token for this bot — a *different* bot from `bot/agent/`.
- A DigitalOcean API token with read+write on droplets and domains.
- A domain already managed by DigitalOcean DNS.
- An SSH keypair whose **public** half is uploaded to DigitalOcean (you need its
  fingerprint) and whose **private** half sits on this host.

## 1. Fill in the environment

```bash
cd bot/infra
cp .env.example .env
$EDITOR .env          # TELEGRAM_BOT_TOKEN, ALLOWED_TELEGRAM_USER_ID,
                      # DO_API_TOKEN, DO_SSH_KEY_FINGERPRINT, DOMAIN,
                      # GOOGLE_CLIENT_ID, SSH_KEY_HOST_PATH
```

Compose reads two env files, in this order:

1. `../../deploy/.env` — optional. If you already keep the DigitalOcean/domain/
   Google values there for the bare-metal scripts, you don't have to repeat them.
2. `./.env` — required. Wins on conflicts.

`SSH_KEY_HOST_PATH` is a **host** path (e.g. `~/.ssh/id_ed25519`). Compose mounts
it read-only at `/run/secrets/ssh_key` and the entrypoint makes a private 0600
copy inside the container, so the host file's mode bits don't matter and `ssh`
won't refuse the key. The `SSH_PRIVATE_KEY` value from `deploy/.env` is ignored
inside the container — a host path means nothing in there.

`SUBDOMAIN`, `SECRET_KEY`, `AGENT_TOKENS` and `TURN_SECRET` are **not** config:
the subdomain comes from the inline keyboard and the three secrets are generated
fresh on every `/up`.

## 2. Build and start

```bash
cd bot/infra
docker compose build          # or: docker compose up -d --build
docker compose up -d
docker compose logs -f
```

A healthy start looks like this:

```
infra-bot-1  | entrypoint: ready (domain=example.com, state=/data/infra-state.json)
infra-bot-1  | 2026-10-07 16:36:47 INFO bot-infra: Infra bot starting (allowed user id 424242)
```

Then send `/up` to the bot in Telegram.

If the token is wrong you'll see `telegram.error.InvalidToken: … was rejected by
the server.` and — because of `restart: unless-stopped` — the container will loop
on restart until you fix `.env` and run `docker compose up -d --force-recreate`.

If a required variable is missing the container stops before touching Telegram:

```
entrypoint: missing required env var(s): DO_API_TOKEN DOMAIN
```

## 3. State (read this before you `docker rm` anything)

Two files live on the named volume `infra_state`, mounted at `/data`:

| File in container | What it holds | Why it must survive |
|---|---|---|
| `/data/infra-state.json` | status, subdomain, fqdn, per-deploy secrets | `/down` needs the secrets to rebuild the deploy config |
| `/data/deploy-state.json` | droplet id, ip, name, fqdn | without it `/down` cannot find the droplet to delete |

The paths come from `INFRA_BOT_STATE_PATH` / `RC_DEPLOY_STATE_PATH`
(`bot/infra/Dockerfile`), honoured by `bot/infra/state.py:19` and
`deploy/rc_deploy/state.py:7`. Bare-metal runs without those vars keep using
`bot/infra/.state.json` and `deploy/.state.json` as before.

**If you destroy the volume while a droplet is up, the bot can no longer tear it
down and you keep paying.** Delete the droplet in the DigitalOcean dashboard in
that case.

## 4. Update after a code change

The image bakes in `deploy/`, `server/` and `web/` because `/up` rsyncs them to
the droplet. Any change there — or in the bot itself — needs a rebuild:

```bash
cd bot/infra
docker compose up -d --build
```

The state volume is untouched by a rebuild, so this is safe while a deploy is
live. Plain `docker compose up -d` will silently keep running the old
`rc-infra-bot:latest` image, so don't skip `--build`.

## 5. Reset the state

Only do this when nothing is deployed (or you have already deleted the droplet
by hand).

```bash
cd bot/infra
docker compose down          # stop, keep state
docker compose down -v       # stop AND wipe the state volume
```

Inspect or surgically fix state without wiping it:

```bash
docker compose exec infra-bot cat /data/infra-state.json
docker compose exec infra-bot rm /data/infra-state.json   # "stuck deploying"
```

`docker compose restart` and host reboots are both safe: `restart: unless-stopped`
brings the bot back and the state is on the volume.

## 6. Troubleshooting

| Symptom | Cause |
|---|---|
| Container runs but the bot never answers | You are running an **old** image whose `CMD` was `/bin/sh`. `docker compose ps` shows `COMMAND "/bin/sh"` instead of `"/usr/local/bin/dock…"`. Rebuild with `--build`. |
| `Conflict. The container name "/rc-infra-bot" is already in use` | A leftover hand-rolled `docker run --name rc-infra-bot` container. Remove it: `docker rm -f rc-infra-bot`. Compose names its own container `rc-infra-infra-bot-1`. |
| `entrypoint: no deploy SSH key` | `SSH_KEY_HOST_PATH` points at a file that doesn't exist, so Docker mounted a directory (or nothing) there. Use an absolute path. |
| Deploy fails at `preflight: SSH private key not found` | Same as above, from the Python side. |
| `Config error: Required vars missing` in chat | The entrypoint rendered `/app/deploy/.env` without a var the deploy code needs. Check with `docker compose exec infra-bot cat /app/deploy/.env`. |
| Bot silent after `/up` | `ALLOWED_TELEGRAM_USER_ID` doesn't match your Telegram user id — unauthorized users get no reply by design. |

Logs are capped at 3 × 10 MB by the compose `logging` block; `docker compose
logs -f` is the only place the deploy tracebacks show up.
