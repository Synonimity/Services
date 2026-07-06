# SynonTech Microservices Template Library

A standardized set of drop-in Python services for every new build. Goal: any new product starts with infra already solved, only business logic left to write.

## Core design principle

**Every template must work when dropped into a single project's existing FastAPI app and database, with zero required network calls to any other KerfSuite service.** Concretely: a template is a Python package (models + service class + an optional router for anything that genuinely needs an HTTP endpoint, like a webhook). The host project's own app supplies the DB session and config; the template never owns its own `main.py`, its own database connection, or its own `.env`.

This means **Auth defaults to independent accounts per project** — dropping the auth template into Project A and Project B gives each its own users table and its own logins, not a shared identity. That's deliberate: shared login (SSO) across multiple KerfSuite products is a real thing you might want someday, but it's a separate, opt-in piece of architecture for whichever specific products need it — not something every product is implicitly signed up for just by using the template.

**Two named exceptions, because their entire value proposition requires centralization:**

| Service | Why it has to stay centralized |
|---|---|
| **Env/Secrets** | The whole point is one source of truth across projects. A copy-in version would just be N separate secret stores, which is the opposite of the point. |
| **Observability** (logging + error tracking) | The payoff is seeing logs/errors across *all* products in one place. Copy-in means each product only ever sees its own — the cross-product view, which is most of the value, disappears. |

Everything else in this library — including Auth, despite originally being built as a standalone service — follows the copy-in default.

## Already built

| Service | Pattern | Status |
|---|---|---|
| Auth & login | Copy-in (default) | Built as standalone service; **retrofit to copy-in is the next piece of work** |
| Billing | Copy-in (default) | **Standardized (Copy-in)** |
| Notifications | Copy-in (default) | **Standardized (Copy-in)** |
| Webhooks | Copy-in (default) | **Standardized (Copy-in)** |
| Licensing / Entitlements | Copy-in (default) | **Standardized (Copy-in)** |
| Background Jobs / Task Queue | Copy-in (default) | **Standardized (Copy-in)** |
| Caching | Copy-in (default) | **Standardized (Copy-in)** |
| Rate Limiting | Copy-in (default) | **Standardized (Copy-in)** |
| LLM Caller | Copy-in (default) | **Standardized (Copy-in)** |
| LLM Guard | Copy-in (default) | **Standardized (Copy-in)** |
| Context Assembler | Copy-in (default) | **Standardized (Copy-in)** |
| Usage Tracker | Copy-in (default) | **Standardized (Copy-in)** |
| Error handling & logging | Centralized (named exception) | Built correctly as a standalone service — no change needed |
| Env handling | Centralized (named exception) | Built correctly as a standalone service — no change needed |

---

## Tier 1 — AI & LLM Orchestration (Built & High Value)

| Service | What it does | Why it's here |
|---|---|---|
| **LLM Caller** | Minimal microservice for calling an LLM API (Anthropic, OpenAI, etc.). | Unifies how products talk to models. Env-driven endpoint/key/model config. |
| **LLM Guard** | Injection risk scoring + PII scrubbing. | First line of defense for user-facing LLM features. Zero-latency, rule-based security. |
| **Context Assembler** | Priority-based context trimming and assembly. | Solves the "stuffing facts/history into a budget" problem deterministically. |
| **Usage Tracker** | Token/cost tracking + plan-based quotas. | Replaces/implements Metrics/Telemetry. Tracks exactly what AI features cost per user. |

---

## Tier 2 — Strong candidates, build when the next product needs them

| Service | What it does | Notes |
|---|---|---|
| **File Storage / Uploads** | Presigned URLs, type/size validation, virus scan hook | Wraps Supabase Storage or S3. Needed for KerfCAM (DXF/SVG uploads) eventually. Copy-in. |
| **Audit Trail** | "Who did what, when" — distinct from error logs | You already flagged this gap for SoulLink's NSFW audit trail. *Worth a second look like Observability got* — if you ever want one cross-product audit view rather than per-product trails, this might belong in the centralized-exception column instead of copy-in. Revisit when it's actually being built. |
| **Health Checks** | `/health`, `/ready` endpoints, dependency pings (DB, Redis, etc.) | Trivial but every service needs one — template it once, never write it again. Copy-in. |
| **Search** | Postgres full-text or pgvector wrapper | Relevant for SoulLink's semantic memory/lore needs down the line. Copy-in. |
| **Feature Flags** | Toggle features per-user, per-product, per-environment | Useful once you've got multiple products at different maturity stages (you already do). *Same flag as Audit Trail* — if you want to flip a flag once and have it apply across products, that's a centralization argument. |

---

## Tier 3 — Lower urgency / situational

| Service | What it does | Notes |
|---|---|---|
| **Onboarding** | First-run flows, tutorial state, setup wizards | More business-logic-shaped than infra-shaped — maybe a *pattern/checklist* rather than a generic module. |
| **Config / Feature Toggle Sync** | Centralized config service products can poll | Only worth it once you have 4+ live products needing live config changes without redeploy. This one's explicitly a centralization candidate. |
| **Multi-tenant Data Isolation Helper** | RLS policy generator/validator | You've hand-audited RLS issues (KerfSuite). A dev-time tool, not a runtime service. |
| **PDF / Document Generation** | Invoices, reports, license certificates | Useful for KerfPortal receipts, KerfStock reports. Copy-in. |
| **Internationalization (i18n)** | String table + locale switching | Only if/when you go beyond English-only products. Copy-in. |

---

## Suggested build order (Remaining Work)

1. **Auth Retrofit** — Convert the standalone `auth_service` into the standard copy-in module pattern.
2. **Tier 2 Services** — As each becomes relevant to the next product (File Storage, Search, etc.).
3. **Audit Trail / Feature Flags** — Decide on Centralized vs. Copy-in before building.

## Standardization checklist for each service

To keep the library actually interchangeable (not just a folder of similar-but-different code), each service should ship with:

- [ ] Consistent package structure (matches the retrofitted Auth/Billing/Notifications shape: `models.py`, a `*Config` Pydantic model, a `*Service` class, an optional `router()` for anything that genuinely needs an HTTP endpoint)
- [ ] `schema.sql` documenting the tables it needs, run once in the host project's own Supabase project
- [ ] Standalone `README.md` — what it does, how to wire it into a host app, config options
- [ ] Uses the centralized error-handling/logging service internally for anything worth tracking across products (no duplicate logging logic)
- [ ] Config comes from the host app — never its own `.env` loading
- [ ] Tests for the "unhappy path" (auth fails, webhook signature invalid, cache miss, etc.)
- [ ] No hard dependency on other template modules — each one should work if copied in alone, with optional integration if your other modules are also present
- [ ] Self-contained `requirements.txt` snippet (or a clearly marked block in one) so you know exactly what to add when you copy it in

**Convention: copy-in modules by default, centralized services only where the entire value proposition requires it.**

---

*Generated for SynonTech's microservices template library initiative — June 2026. Updated July 2026 to reflect completion of Tier 1 infra and addition of LLM Orchestration modules.*
