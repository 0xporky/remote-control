# Bot Directory Index

This directory holds **two independent Telegram bots** that together replace the previous unified bot. They run on different machines and share no filesystem.

- **`infra/`** — runs on a Linux host. Owns DigitalOcean lifecycle: `/up` provisions the droplet via `deploy/rc_deploy`; `/down` tears it down. See [`infra/CLAUDE.md`](infra/CLAUDE.md).
- **`agent/`** — runs on the Windows desktop being controlled. Owns the desktop-agent subprocess: `/up` starts `agent/main.py`; `/down` stops it. See [`agent/CLAUDE.md`](agent/CLAUDE.md).

## Cross-bot contract: the credentials blob

The two bots are connected only through a single base64-urlsafe-encoded JSON payload that the user copy-pastes from the Infra bot's `/up` success message into the Agent bot's chat after picking a subdomain there.

Payload (decoded):

```json
{
  "v": 1,
  "sub": "rc1",
  "fqdn": "rc1.example.com",
  "agent_token": "<urlsafe base64>",
  "turn_secret": "<urlsafe base64>"
}
```

`SECRET_KEY` is deliberately not included — it lives only on the Linux host.

Producers/consumers:
- Producer: `bot/infra/handlers.py:_encode_blob()` (constant `_BLOB_VERSION`).
- Consumer: `bot/agent/handlers.py:_decode_blob()` (constant `_EXPECTED_BLOB_VERSION`).

If the schema changes, bump both constants in the same change.

## Recommended `/up` and `/down` order

`/up`: Infra first → copy blob → Agent next.
`/down`: Agent first → then Infra (so the agent doesn't sit in a reconnect loop while the droplet vanishes).

Each bot has its own `SUBDOMAIN_CHOICES` list (`rc, rc1, rc2, rc3`); keep them in sync.
