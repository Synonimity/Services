"""
synon_health.checks
---------------------
Factory functions that build individual health check callables.

Each factory takes whatever client/backend it needs to test and returns
an `async def check() -> CheckResult` closure. This keeps synon_health
itself dependency-free — it never imports supabase, redis, or other
synon_* modules directly. The host app wires the concrete clients in.
"""
