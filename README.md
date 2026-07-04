# SynonTech Services Library

> A growing collection of production-ready, drop-in Python services for every new SynonTech product. Start a new build with the infra already solved — only business logic left to write.

---

## Table of Contents

- [Architecture Philosophy](#architecture-philosophy)
- [Service Catalogue](#service-catalogue)
  - [Centralized Services](#-centralized-services)
  - [Tier 1 — AI & LLM Orchestration](#tier-1--ai--llm-orchestration)
  - [Tier 2 — Core Infra](#tier-2--core-infra)
  - [Tier 3 — Planned](#tier-3--planned)
- [How to Use a Service](#how-to-use-a-service)
- [Standardization Checklist](#standardization-checklist)
- [Build Roadmap](#build-roadmap)
- [Contributing a New Service](#contributing-a-new-service)

---

## Architecture Philosophy

**Every service in this library is a drop-in Python package** — a set of models, a service class, and an optional router — that plugs into a host project's existing FastAPI app and database. No service owns its own `main.py`, its own database connection, or its own `.env`. The host project supplies everything; the service supplies the logic.

### Copy-in by default

The default pattern is **copy-in**: you literally copy the package folder into your project. This gives each project its own independent instance of that service with zero coupling to any other SynonTech product. Dropping Auth into Project A and Project B gives each its own users table and its own logins — deliberately. Shared SSO across products is a real architectural option, but it's an explicit opt-in decision, not a hidden side-effect.

### Centralized where it must be

Two services break the copy-in rule because their entire value proposition *requires* a single source of truth:

| Service | Why centralized |
|---|---|
| **Env / Secrets** (`env_service`) | One source of truth across all products. N copies = N separate secret stores, which defeats the point. |
| **Observability** (`observability_service`) | Cross-product log and error visibility. Per-product copies only ever see their own data — the cross-product view, which is most of the value, disappears. |

Everything else follows the copy-in default.

---

## Service Catalogue

### 🔒 Centralized Services

These run as standalone services. All other products connect to them — they are **never** copied in.

| Folder | Service | Description |
|---|---|---|
| `env_service/` | **Env & Secrets** | Single source of truth for environment variables and secrets across all SynonTech products. |
| `observability_service/` | **Observability** | Centralized logging and error tracking. Gives a cross-product view of logs and errors in one place. |

---

### Tier 1 — AI & LLM Orchestration

> ✅ Built & production-ready. These are copy-in modules.

| Folder | Service | Description |
|---|---|---|
| `llm_caller/` | **LLM Caller** | Minimal, unified interface for calling LLM APIs (Anthropic, OpenAI, etc.). Env-driven model/key/endpoint config. |
| `llm_guard/` | **LLM Guard** | Prompt injection risk scoring + PII scrubbing. Zero-latency, rule-based security layer — runs before any LLM call hits the model. |
| `context_assembler/` | **Context Assembler** | Priority-based context trimming and assembly. Solves the "fitting facts and history into a token budget" problem deterministically. |
| `usage_tracker/` | **Usage Tracker** | Token and cost tracking with plan-based quota enforcement. Tracks exactly what AI features cost per user per product. |

---

### Tier 2 — Core Infra

> ✅ Built & production-ready. All are copy-in modules unless noted.

| Folder | Service | Description |
|---|---|---|
| `auth_service/` | **Auth & Login** | Full authentication stack (users, sessions, JWT). *Currently standalone — Auth Retrofit to copy-in pattern is the next piece of work.* |
| `billing/` / `billing_service/` | **Billing** | Subscription and payment handling. Wraps Stripe. Copy-in. |
| `notifications/` / `notifications_service/` | **Notifications** | Email, push, and in-app notification dispatch. Copy-in. |
| `webhooks_service/` | **Webhooks** | Outbound webhook delivery with signature signing and retry logic. Copy-in. |
| `licensing_service/` | **Licensing & Entitlements** | Feature gating and license key management. Copy-in. |
| `scheduler_service/` | **Background Jobs / Task Queue** | Async background job scheduling and task queue. Copy-in. |
| `caching_service/` / `response_cache/` | **Caching** | General-purpose caching layer. Copy-in. |
| `ratelimit_service/` | **Rate Limiting** | Per-user and per-endpoint rate limiting. Copy-in. |
| `fallback_router/` | **Fallback Router** | Graceful fallback routing for failed or unavailable services. Copy-in. |

---

### Tier 3 — Planned

> 🔲 Not yet built. Included here for visibility and to lock in design decisions before implementation.

| Service | Description | Pattern | Notes |
|---|---|---|---|
| **File Storage / Uploads** | Presigned URLs, type/size validation, virus scan hook. Wraps Supabase Storage or S3. | Copy-in | Needed for file-heavy products (e.g. DXF/SVG uploads). |
| **Audit Trail** | Immutable "who did what, when" log — distinct from error logs. | TBD | Revisit centralized vs. copy-in before building. Cross-product audit view may justify centralization. |
| **Health Checks** | `/health` and `/ready` endpoints with DB/Redis dependency pings. | Copy-in | Trivial but every service needs one. Template it once. |
| **Search** | Postgres full-text or `pgvector` wrapper for semantic search. | Copy-in | Relevant for semantic memory / lore features. |
| **Feature Flags** | Toggle features per-user, per-product, or per-environment. | TBD | Same centralization question as Audit Trail — if flags need to flip across products simultaneously, centralize. |
| **PDF / Document Generation** | Invoices, reports, license certificates. | Copy-in | Useful for receipt and reporting features. |
| **Multi-tenant RLS Helper** | RLS policy generator and validator. | Dev-time tool | Addresses hand-audited RLS policy gaps. Not a runtime service. |
| **Onboarding** | First-run flows, tutorial state, setup wizards. | Pattern / checklist | More business-logic-shaped than infra — likely a *pattern* rather than a generic module. |
| **i18n** | String table and locale switching. | Copy-in | Only if/when products go beyond English. |

---

## How to Use a Service

1. **Copy the service folder** into your host project (e.g. `cp -r /path/to/Services/billing_service ./your_project/`).
2. **Install dependencies** — each service has a `requirements.txt` snippet or a clearly marked block listing what to add.
3. **Run the schema** — each service ships a `schema.sql`. Run it once against your project's own Supabase instance.
4. **Wire up config** — instantiate the service's `*Config` Pydantic model from your host app's config/env, and pass it in. The service never loads its own `.env`.
5. **Register the router** (if the service has one) — call `service.router()` and include it in your FastAPI app.
6. **Read the service's own `README.md`** for any service-specific wiring details.

```python
# Example: wiring in the billing service
from billing_service import BillingConfig, BillingService, billing_router

billing_config = BillingConfig(
    stripe_secret_key=settings.STRIPE_SECRET_KEY,
    webhook_secret=settings.STRIPE_WEBHOOK_SECRET,
)
billing = BillingService(config=billing_config, db=db_session)

app.include_router(billing_router(billing))
```

---

## Standardization Checklist

Every service in this library ships with all of the following. No exceptions.

- [ ] **Consistent package structure** — `models.py`, a `*Config` Pydantic model, a `*Service` class, and an optional `router()` for anything that genuinely needs an HTTP endpoint.
- [ ] **`schema.sql`** — documents the tables the service needs, run once in the host project's own database.
- [ ] **Standalone `README.md`** — what it does, how to wire it into a host app, all config options.
- [ ] **Centralized logging** — uses `observability_service` internally for anything worth tracking across products. No duplicate logging logic.
- [ ] **Host-supplied config** — config comes from the host app. The service never loads its own `.env`.
- [ ] **Unhappy-path tests** — auth failure, invalid webhook signature, cache miss, quota exceeded, etc.
- [ ] **No hard inter-module dependencies** — each service works if copied in alone. Integration with other library modules is optional, never required.
- [ ] **`requirements.txt` snippet** — clearly marked block of dependencies to add to the host project.

---

## Build Roadmap

### Immediate

1. **Auth Retrofit** — Convert `auth_service` from standalone service to the standard copy-in module pattern (matching the shape of Billing, Notifications, etc.).

### Next (as each product needs it)

2. **File Storage / Uploads** — Build when the first product requires file handling.
3. **Health Checks** — Simple, high-value, template it once.
4. **Search** — Build when semantic search is needed.

### Design decisions required before building

5. **Audit Trail** — Decide centralized vs. copy-in. Build once decided.
6. **Feature Flags** — Same decision required. Build once decided.

---

## Contributing a New Service

1. Create a new folder under `Services/` named `<service_name>_service/` (or just `<service_name>/` for clearly named short modules).
2. Follow the [Standardization Checklist](#standardization-checklist) in full before merging.
3. Update this README — add the service to the appropriate tier in the [Service Catalogue](#service-catalogue).
4. Update [`microservices-template-library.md`](./microservices-template-library.md) with the new entry and its status.

---

*SynonTech Services Library — maintained by the SynonTech team. Started June 2026.*
