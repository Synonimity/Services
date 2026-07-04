"""
The baseline catalog. Each entry documents the env vars a given
integration needs, which are required vs optional, and which are
sensitive (so the CLI/UI can mask them by default). This is reference
data, not stored in the database - add a new provider by adding an entry
here, no migration needed.

A project is assigned one or more template keys (e.g. a typical KerfSuite
service might be ["app_core", "postgresql", "sentry"]); validation then
checks the project's actual stored keys against the union of its
templates' required vars.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class EnvVarSpec:
    name: str
    required: bool = True
    sensitive: bool = True
    description: str = ""
    example: str = ""


@dataclass(frozen=True)
class EnvTemplate:
    key: str
    display_name: str
    description: str
    vars: list[EnvVarSpec] = field(default_factory=list)


CATALOG: dict[str, EnvTemplate] = {}


def _register(template: EnvTemplate) -> None:
    CATALOG[template.key] = template


# ---------------------------------------------------------------------------
# Core app config - the baseline every one of these FastAPI services uses
# ---------------------------------------------------------------------------
_register(EnvTemplate(
    key="app_core",
    display_name="App Core",
    description="The baseline every service needs regardless of what it does.",
    vars=[
        EnvVarSpec("ENVIRONMENT", required=True, sensitive=False, description="development | staging | production", example="production"),
        EnvVarSpec("BASE_URL", required=True, sensitive=False, description="Public URL this service is reachable at", example="https://api.yourapp.com"),
        EnvVarSpec("ALLOWED_ORIGINS", required=False, sensitive=False, description="Comma-separated CORS origins", example="https://app.yourapp.com"),
        EnvVarSpec("SERVICE_API_KEY", required=True, sensitive=True, description="Shared secret for service-to-service calls"),
        EnvVarSpec("LOG_LEVEL", required=False, sensitive=False, description="debug | info | warning | error", example="info"),
    ],
))

# ---------------------------------------------------------------------------
# Databases
# ---------------------------------------------------------------------------
_register(EnvTemplate(
    key="postgresql",
    display_name="PostgreSQL",
    description="Direct Postgres connection (Supabase, RDS, Railway, self-hosted, etc.)",
    vars=[
        EnvVarSpec("DATABASE_URL", required=True, sensitive=True, description="postgresql(+asyncpg)://user:pass@host:port/db"),
    ],
))

_register(EnvTemplate(
    key="mysql",
    display_name="MySQL",
    description="Direct MySQL connection.",
    vars=[
        EnvVarSpec("DATABASE_URL", required=True, sensitive=True, description="mysql+aiomysql://user:pass@host:port/db"),
    ],
))

_register(EnvTemplate(
    key="supabase",
    display_name="Supabase",
    description="Supabase project credentials, on top of (not instead of) DATABASE_URL if you also use Supabase's client libraries / auth / storage.",
    vars=[
        EnvVarSpec("SUPABASE_URL", required=True, sensitive=False, example="https://xxxx.supabase.co"),
        EnvVarSpec("SUPABASE_ANON_KEY", required=True, sensitive=True, description="Public/anon key - safe for frontend use, but still treat as config not literal source code"),
        EnvVarSpec("SUPABASE_SERVICE_ROLE_KEY", required=False, sensitive=True, description="Bypasses Row Level Security entirely - backend only, NEVER ship this to a client"),
    ],
))

_register(EnvTemplate(
    key="upstash_redis",
    display_name="Upstash Redis",
    description="Serverless Redis over REST - common for rate limiting, caching, queues.",
    vars=[
        EnvVarSpec("UPSTASH_REDIS_REST_URL", required=True, sensitive=False),
        EnvVarSpec("UPSTASH_REDIS_REST_TOKEN", required=True, sensitive=True),
    ],
))

_register(EnvTemplate(
    key="redis_generic",
    display_name="Redis (generic)",
    description="A traditional Redis connection string instead of Upstash's REST API.",
    vars=[
        EnvVarSpec("REDIS_URL", required=True, sensitive=True, example="redis://default:pass@host:6379"),
    ],
))

# ---------------------------------------------------------------------------
# Observability / error tracking
# ---------------------------------------------------------------------------
_register(EnvTemplate(
    key="sentry",
    display_name="Sentry",
    description="Error tracking / performance monitoring.",
    vars=[
        EnvVarSpec("SENTRY_DSN", required=True, sensitive=True),
        EnvVarSpec("SENTRY_ENVIRONMENT", required=False, sensitive=False, example="production"),
        EnvVarSpec("SENTRY_TRACES_SAMPLE_RATE", required=False, sensitive=False, example="0.1"),
    ],
))

# ---------------------------------------------------------------------------
# Email / messaging
# ---------------------------------------------------------------------------
_register(EnvTemplate(
    key="resend",
    display_name="Resend",
    description="Transactional email provider.",
    vars=[
        EnvVarSpec("RESEND_API_KEY", required=True, sensitive=True),
        EnvVarSpec("RESEND_WEBHOOK_SECRET", required=False, sensitive=True),
        EnvVarSpec("EMAIL_FROM_ADDRESS", required=True, sensitive=False),
    ],
))

_register(EnvTemplate(
    key="smtp",
    display_name="SMTP",
    description="Generic SMTP credentials, if not using a transactional email API.",
    vars=[
        EnvVarSpec("SMTP_HOST", required=True, sensitive=False),
        EnvVarSpec("SMTP_PORT", required=True, sensitive=False, example="587"),
        EnvVarSpec("SMTP_USER", required=True, sensitive=True),
        EnvVarSpec("SMTP_PASSWORD", required=True, sensitive=True),
    ],
))

_register(EnvTemplate(
    key="slack_webhook",
    display_name="Slack (Incoming Webhook)",
    description="Ops alerts to a Slack channel.",
    vars=[EnvVarSpec("SLACK_WEBHOOK_URL", required=True, sensitive=True)],
))

_register(EnvTemplate(
    key="discord_webhook",
    display_name="Discord (Webhook)",
    description="Ops alerts to a Discord channel.",
    vars=[EnvVarSpec("DISCORD_WEBHOOK_URL", required=True, sensitive=True)],
))

_register(EnvTemplate(
    key="sms_clickatell",
    display_name="Clickatell (SMS)",
    description="South African SMS provider.",
    vars=[
        EnvVarSpec("CLICKATELL_API_KEY", required=True, sensitive=True),
    ],
))

# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------
_register(EnvTemplate(
    key="payfast",
    display_name="PayFast",
    description="South African payment gateway.",
    vars=[
        EnvVarSpec("PAYFAST_MERCHANT_ID", required=True, sensitive=True),
        EnvVarSpec("PAYFAST_MERCHANT_KEY", required=True, sensitive=True),
        EnvVarSpec("PAYFAST_PASSPHRASE", required=True, sensitive=True),
        EnvVarSpec("PAYFAST_MODE", required=True, sensitive=False, description="sandbox | live"),
    ],
))

_register(EnvTemplate(
    key="stripe",
    display_name="Stripe",
    description="Not available for South African merchant accounts as of this writing, included for projects/clients elsewhere.",
    vars=[
        EnvVarSpec("STRIPE_SECRET_KEY", required=True, sensitive=True),
        EnvVarSpec("STRIPE_WEBHOOK_SECRET", required=True, sensitive=True),
        EnvVarSpec("STRIPE_PUBLISHABLE_KEY", required=False, sensitive=False),
    ],
))

# ---------------------------------------------------------------------------
# OAuth providers
# ---------------------------------------------------------------------------
_register(EnvTemplate(
    key="oauth_google",
    display_name="OAuth - Google",
    description="",
    vars=[
        EnvVarSpec("GOOGLE_CLIENT_ID", required=True, sensitive=False),
        EnvVarSpec("GOOGLE_CLIENT_SECRET", required=True, sensitive=True),
    ],
))

_register(EnvTemplate(
    key="oauth_facebook",
    display_name="OAuth - Facebook",
    description="",
    vars=[
        EnvVarSpec("FACEBOOK_CLIENT_ID", required=True, sensitive=False),
        EnvVarSpec("FACEBOOK_CLIENT_SECRET", required=True, sensitive=True),
    ],
))

_register(EnvTemplate(
    key="oauth_discord",
    display_name="OAuth - Discord",
    description="",
    vars=[
        EnvVarSpec("DISCORD_CLIENT_ID", required=True, sensitive=False),
        EnvVarSpec("DISCORD_CLIENT_SECRET", required=True, sensitive=True),
    ],
))

_register(EnvTemplate(
    key="oauth_apple",
    display_name="OAuth - Apple (Sign in with Apple)",
    description="",
    vars=[
        EnvVarSpec("APPLE_CLIENT_ID", required=True, sensitive=False, description="Your Services ID"),
        EnvVarSpec("APPLE_TEAM_ID", required=True, sensitive=False),
        EnvVarSpec("APPLE_KEY_ID", required=True, sensitive=False),
        EnvVarSpec("APPLE_PRIVATE_KEY_PATH", required=True, sensitive=True, description="Path to the .p8 key file - the file itself isn't stored here, just the path"),
    ],
))

# ---------------------------------------------------------------------------
# Auth / crypto primitives
# ---------------------------------------------------------------------------
_register(EnvTemplate(
    key="jwt_rs256",
    display_name="JWT (RS256)",
    description="Asymmetric JWT signing, e.g. the KerfSuite auth service.",
    vars=[
        EnvVarSpec("JWT_PRIVATE_KEY_PATH", required=True, sensitive=True),
        EnvVarSpec("JWT_PUBLIC_KEY_PATH", required=True, sensitive=False),
        EnvVarSpec("JWT_ISSUER", required=False, sensitive=False),
        EnvVarSpec("JWT_AUDIENCE", required=False, sensitive=False),
    ],
))

# ---------------------------------------------------------------------------
# Cloud storage
# ---------------------------------------------------------------------------
_register(EnvTemplate(
    key="cloudflare_r2",
    display_name="Cloudflare R2",
    description="S3-compatible object storage, no egress fees.",
    vars=[
        EnvVarSpec("R2_ACCOUNT_ID", required=True, sensitive=False),
        EnvVarSpec("R2_ACCESS_KEY_ID", required=True, sensitive=True),
        EnvVarSpec("R2_SECRET_ACCESS_KEY", required=True, sensitive=True),
        EnvVarSpec("R2_BUCKET_NAME", required=True, sensitive=False),
    ],
))

_register(EnvTemplate(
    key="aws_s3",
    display_name="AWS S3",
    description="",
    vars=[
        EnvVarSpec("AWS_ACCESS_KEY_ID", required=True, sensitive=True),
        EnvVarSpec("AWS_SECRET_ACCESS_KEY", required=True, sensitive=True),
        EnvVarSpec("AWS_REGION", required=True, sensitive=False),
        EnvVarSpec("S3_BUCKET_NAME", required=True, sensitive=False),
    ],
))

# ---------------------------------------------------------------------------
# AI providers - relevant given the multi-model workflow
# ---------------------------------------------------------------------------
_register(EnvTemplate(
    key="anthropic_ai",
    display_name="Anthropic API",
    description="",
    vars=[EnvVarSpec("ANTHROPIC_API_KEY", required=True, sensitive=True)],
))

_register(EnvTemplate(
    key="openai_ai",
    display_name="OpenAI API",
    description="",
    vars=[EnvVarSpec("OPENAI_API_KEY", required=True, sensitive=True)],
))

_register(EnvTemplate(
    key="groq_ai",
    display_name="Groq API",
    description="",
    vars=[EnvVarSpec("GROQ_API_KEY", required=True, sensitive=True)],
))

# ---------------------------------------------------------------------------
# Misc commonly-needed
# ---------------------------------------------------------------------------
_register(EnvTemplate(
    key="google_maps",
    display_name="Google Maps",
    description="",
    vars=[EnvVarSpec("GOOGLE_MAPS_API_KEY", required=True, sensitive=True)],
))

_register(EnvTemplate(
    key="captcha_turnstile",
    display_name="Cloudflare Turnstile (CAPTCHA)",
    description="",
    vars=[
        EnvVarSpec("TURNSTILE_SITE_KEY", required=True, sensitive=False),
        EnvVarSpec("TURNSTILE_SECRET_KEY", required=True, sensitive=True),
    ],
))

_register(EnvTemplate(
    key="generic_api_key",
    display_name="Generic API Key",
    description="Catch-all for a one-off integration that doesn't warrant its own template - assign this and store whatever key name you need.",
    vars=[],
))


def list_templates() -> list[EnvTemplate]:
    return sorted(CATALOG.values(), key=lambda t: t.key)


def get_template(key: str) -> EnvTemplate | None:
    return CATALOG.get(key)


def required_vars_for(template_keys: list[str]) -> dict[str, EnvVarSpec]:
    """Union of required vars across the given templates, keyed by var name."""
    result: dict[str, EnvVarSpec] = {}
    for key in template_keys:
        template = CATALOG.get(key)
        if not template:
            continue
        for var in template.vars:
            if var.required:
                result[var.name] = var
    return result


def all_known_vars_for(template_keys: list[str]) -> dict[str, EnvVarSpec]:
    """Every var (required or optional) across the given templates, keyed by name."""
    result: dict[str, EnvVarSpec] = {}
    for key in template_keys:
        template = CATALOG.get(key)
        if not template:
            continue
        for var in template.vars:
            result[var.name] = var
    return result
