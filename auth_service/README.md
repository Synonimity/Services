# KerfSuite Auth Service

A standalone FastAPI authentication microservice: username/password accounts
plus OAuth2 login via Google, Facebook, Discord, and Apple, backed by a
Supabase Postgres database.

## Security design summary

| Concern | Approach |
|---|---|
| Password storage | Argon2id (OWASP-recommended), via passlib |
| Access tokens | JWT, RS256 (asymmetric) — other services verify with the public key only, never the signing key |
| Refresh tokens | Opaque random strings; only a SHA-256 hash is stored; rotated (single-use) on every refresh |
| Brute force | Per-account lockout after N failed logins; IP-based rate limiting on all auth/oauth endpoints |
| User enumeration | Login returns identical error for "no such user" and "wrong password," with constant-ish timing |
| OAuth CSRF | Signed, expiring `state` token (itsdangerous) — no server-side session needed |
| OAuth code interception | PKCE (S256) on every provider that supports it |
| Apple identity | id_token signature verified against Apple's live JWKS, not trusted blindly |
| Transport | HTTPS enforced in production (redirect middleware + HSTS); Supabase Postgres connection is TLS by default |
| DB exposure | Tables created with Row Level Security on and zero policies, so Supabase's auto-REST API can't reach them — only this service's direct DB connection can |
| Headers | X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy, HSTS |
| Error handling | Unhandled exceptions return a generic 500, never a stack trace |

## 1. Set up Supabase

1. Create a project at supabase.com.
2. In the SQL editor, run `schema.sql` from this repo.
3. Go to **Project Settings → Database → Connection string**, choose the
   **Connection pooling** URI (port 6543), and use it as `DATABASE_URL` —
   just change `postgresql://` to `postgresql+asyncpg://`.

## 2. Generate your JWT signing keypair

```bash
mkdir -p keys
openssl genrsa -out keys/private.pem 2048
openssl rsa -in keys/private.pem -pubout -out keys/public.pem
```

Keep `private.pem` secret — only this auth service needs it. Any other
KerfSuite app that needs to verify tokens only needs `public.pem`.

## 3. Register OAuth apps

For each provider, the redirect/callback URI to register is:
`{BASE_URL}/oauth/{provider}/callback` (e.g.
`https://auth.kerfsuite.com/oauth/google/callback`).

- **Google** — [Google Cloud Console](https://console.cloud.google.com/apis/credentials) → OAuth client ID → Web application.
- **Facebook** — [Meta for Developers](https://developers.facebook.com/) → create app → Facebook Login product → add the redirect URI.
- **Discord** — [Discord Developer Portal](https://discord.com/developers/applications) → New Application → OAuth2 → add redirect.
- **Apple** — [Apple Developer](https://developer.apple.com/account/resources/identifiers/list/serviceId) → create a Services ID (this is your `APPLE_CLIENT_ID`) → enable "Sign in with Apple" → register the domain and the redirect URI → separately create a "Sign in with Apple" **key**, download the `.p8` file once (Apple won't let you re-download it), and note the Key ID and your Team ID.

Fill in all the resulting IDs/secrets in `.env` (copy from `.env.example`).

## 4. Install and run

```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in real values
uvicorn app.main:app --reload   # dev
```

For production, either terminate TLS at a reverse proxy (nginx/Caddy/
Cloudflare) in front of uvicorn, or run uvicorn with its own certificate:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 443 \
  --ssl-keyfile=/path/to/key.pem --ssl-certfile=/path/to/cert.pem
```

Set `ENVIRONMENT=production` in `.env` to enable HSTS, the HTTPS-redirect
middleware, trusted-host checking, and to disable the `/docs` page.

## 5. Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/auth/register` | Create account (username, email, password) |
| POST | `/auth/login` | `{identifier, password}` → access + refresh token |
| POST | `/auth/refresh` | Rotate a refresh token for a new pair |
| POST | `/auth/logout` | Revoke a refresh token |
| GET | `/auth/me` | Current user (requires `Authorization: Bearer <access_token>`) |
| GET | `/oauth/{provider}/authorize` | Returns the URL to redirect the user to |
| GET/POST | `/oauth/{provider}/callback` | Provider redirects here; returns access + refresh token |

`{provider}` is one of `google`, `facebook`, `discord`, `apple`.

## Notes / things to decide for your deployment

- The OAuth callback currently returns the token pair as JSON. In a real
  browser flow you'll likely want it to redirect to your frontend with the
  tokens in a URL fragment (`#access_token=...`) or set them as
  `httponly` cookies instead — fragment/cookie choice depends on whether
  your frontend is a SPA or server-rendered.
- Refresh tokens are returned in the response body here for simplicity.
  Consider moving them to an `httponly`, `secure`, `samesite=strict` cookie
  scoped to `/auth/refresh` so they're never reachable from JS.
- Email verification isn't wired up (no email-sending dependency assumed) —
  `is_verified` exists on the model so you can add a verification-link flow
  later without a migration.
- `MAX_FAILED_LOGINS`/`LOCKOUT_MINUTES` and all rate limits are in
  `.env` / `app/routers/auth.py` if you want different thresholds.
