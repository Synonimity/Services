# KerfSuite Env/Secrets Service

A single source of truth for environment variables and secrets across
every project — a catalog of what each integration needs (Sentry,
Supabase, PostgreSQL/MySQL, Upstash Redis, PayFast, OAuth providers, AI
provider keys, and more), encrypted storage per project/environment, and
a CLI to pull a real `.env` file or validate one against what a project
is supposed to have.

## Read this before deploying it anywhere

This is the highest-value target in your entire stack — it's the one
service that, if compromised, compromises every other service's secrets
along with it. A few things follow from that:

**1. This should not be a public-internet-facing service like the other
four.** The auth/billing/notifications/observability services need to be
reachable by browsers, payment providers, and webhooks. This one only
ever needs to be reachable by you, from your own machine, at the moment
you're setting up or rotating a project's config. Run it:
- on `localhost` while you work, or
- on a small private host reachable only over Tailscale/WireGuard/an SSH
  tunnel, or
- behind the `ALLOWED_CLIENT_IPS` allowlist this service supports, at an
  absolute minimum, if it has to be reachable over the open internet at all.

Given you work from a public library, treat that network as hostile by
default — pull or push secrets through a VPN/tunnel from there, not over
the library's open wifi directly.

**2. Be honest with yourself about what this is and isn't.** This uses
real authenticated encryption (Fernet/AES, tested below — tampering with
a stored value makes it fail to decrypt rather than silently returning
garbage) and project-scoped API keys so a leaked deploy key for one app
doesn't expose every app. But it's a single afternoon's build, not an
audited product. Vault, Doppler, Infisical, and cloud KMS-backed secrets
managers have had vastly more security scrutiny than anything in this
repo. For your highest-stakes secrets — live payment credentials, things
protecting real customer data — weigh that tradeoff deliberately rather
than defaulting into it.

**3. The master key is the one secret you have to protect by hand.**
`MASTER_ENCRYPTION_KEY` encrypts everything else; it can't itself be
stored encrypted by this service without recreating the same problem one
level up. Put it in a password manager. Losing it makes every stored
secret permanently unrecoverable; leaking it compromises all of them.
There's no cleverness that makes this problem go away — every secrets
manager, including the big managed ones, has some version of this at its
root.

## How it's organized

- **Catalog** (`app/templates_catalog.py`) — static reference data, no
  database involved. ~27 built-in templates covering databases, payment,
  email, OAuth, AI providers, cloud storage, and more. Add a new
  integration by adding an entry here.
- **Projects** — one per app (e.g. `kerfportal`, `kerfcut`). Each is
  assigned a list of template keys describing what it's expected to need.
- **Secrets** — encrypted key/value pairs scoped to (project, environment).
- **Project API keys** — scoped to one project, optionally read-only.
  The separate admin key has full access to everything and is meant to
  never leave your own machine.
- **Audit log** — append-only, records *which key* was read/written/
  exported and by whom, never the value itself — safe to read or export
  without leaking anything.

## 1. Set up Supabase

Run `schema.sql`.

## 2. Generate your keys

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # MASTER_ENCRYPTION_KEY
python -c "import secrets; print(secrets.token_urlsafe(48))"                                # SERVICE_ADMIN_KEY
```

## 3. Install and run

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in real values
uvicorn app.main:app --reload --host 127.0.0.1   # localhost only
```

## 4. Set up a project (using the admin key)

```bash
curl -X POST http://localhost:8000/admin/projects \
  -H "X-API-Key: $SERVICE_ADMIN_KEY" -H "Content-Type: application/json" \
  -d '{"slug": "kerfportal", "name": "KerfPortal", "template_keys": ["app_core", "postgresql", "jwt_rs256", "oauth_google"]}'

curl -X POST http://localhost:8000/admin/projects/kerfportal/api-keys \
  -H "X-API-Key: $SERVICE_ADMIN_KEY" -H "Content-Type: application/json" \
  -d '{"label": "deploy-key", "can_write": true}'
# -> returns raw_key ONCE. Save it (e.g. ENV_SERVICE_API_KEY in your CI secrets).
```

## 5. Use the CLI

```bash
export ENV_SERVICE_URL=http://localhost:8000
export ENV_SERVICE_API_KEY=...   # the project key from step 4

# Push your existing local .env into the service the first time
python client/env_cli.py push --project kerfportal --environment production --file .env

# Later, on a fresh machine/checkout:
python client/env_cli.py pull --project kerfportal --environment production --output .env
# writes .env with mode 600 (owner read/write only)

# Before deploying, check nothing required is missing:
python client/env_cli.py validate --project kerfportal --environment production
```

`client/env_cli.py` has no dependency on the rest of this repo besides
`httpx` — copy it into any project.

## 6. Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST/GET/PATCH/DELETE | `/admin/projects...` | admin key | Project CRUD |
| POST/GET/DELETE | `/admin/projects/{slug}/api-keys...` | admin key | Issue/list/revoke project keys |
| GET | `/admin/audit-log` | admin key | Who touched what, when |
| GET | `/templates`, `/templates/{key}` | any valid key | Browse the catalog |
| GET | `/projects/{slug}/secrets/{env}` | project key | List keys (not values) |
| GET | `/projects/{slug}/secrets/{env}/{key}` | project key | Reveal one value (audit logged) |
| PUT | `/projects/{slug}/secrets/{env}` | project key, write scope | Bulk set |
| DELETE | `/projects/{slug}/secrets/{env}/{key}` | project key, write scope | Delete one |
| GET | `/projects/{slug}/secrets/{env}/_/validate` | project key | Missing-required / unrecognized check |
| GET | `/projects/{slug}/secrets/{env}/_/export` | project key, write scope | Full decrypted `.env` text |

`/docs` and `/redoc` are disabled unconditionally — there's no reason an
interactive API explorer for a secrets service should ever be reachable,
dev or not.

## 7. What's tested vs what you should still verify

Tested directly in this repo: encrypt/decrypt round-trip, tamper
detection (a modified ciphertext fails to decrypt rather than returning
garbage), wrong-master-key rejection, the catalog's required/unrecognized
var math, dotenv rendering and parsing round-tripping correctly
(including values with spaces, quotes, and `@` characters), and the CLI's
file-permission hardening (pulled `.env` files come out mode 600).

Not tested here, because it needs a real deployment: the actual HTTP
round trip end-to-end, and the `ALLOWED_CLIENT_IPS` middleware against a
real client IP (it's a straightforward string comparison, but
"straightforward" and "tested against reality" aren't the same thing —
confirm it behaves as expected, especially if you're behind a reverse
proxy where `request.client.host` might be the proxy's IP rather than
the real one, which would need `X-Forwarded-For` handling this doesn't
currently do).

## 8. Extending the catalog

Add a new `EnvTemplate` to `app/templates_catalog.py` — no migration, no
restart-sensitive state, it's just Python data. Worth doing for anything
you reuse across more than one project.
