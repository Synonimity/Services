"""
synon_licensing.store

Supabase-backed persistence for licenses, the pre-generated key pool,
and trial usage tracking.

Same convention as synon_webhooks/synon_scheduler: service_role
client, all writes server-side, zero permissive RLS policies.
"""

from datetime import datetime, timezone
from typing import Optional

from supabase import Client, create_client

from . import config
from .keygen import generate_key_string
from .models import LicenseKey, LicenseSource, LicenseStatus, TrialUsage


class LicensingStore:
    def __init__(self, client: Optional[Client] = None):
        if client is not None:
            self._client = client
        else:
            config.validate_config()
            self._client = create_client(
                config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY
            )
        self._keys_table = config.LICENSE_KEYS_TABLE
        self._pool_table = config.LICENSE_KEY_POOL_TABLE
        self._trial_table = config.TRIAL_USAGE_TABLE

    # ------------------------------------------------------------------
    # Pool management
    # ------------------------------------------------------------------

    def add_to_pool(self, product: str, count: int) -> int:
        """
        Pre-generate `count` unassigned keys for `product` and insert
        into the pool table. Returns the number actually inserted
        (may be less than `count` if a collision retry exhausts
        attempts — extremely unlikely with this keyspace, but the
        unique constraint is there as a backstop).
        """
        rows = []
        for _ in range(count):
            rows.append({"key": generate_key_string(), "product": product, "assigned": False})

        # Insert one at a time so a single collision doesn't fail the
        # whole batch — collisions should be near-impossible at this
        # keyspace size, but "near-impossible" isn't "impossible".
        inserted = 0
        for row in rows:
            try:
                self._client.table(self._pool_table).insert(row).execute()
                inserted += 1
            except Exception:
                continue  # likely a unique constraint hit; skip and move on
        return inserted

    def _pull_from_pool(self, product: str) -> Optional[str]:
        """
        Atomically claims one unassigned key from the pool via the
        `claim_pool_key` Postgres function (see schema.sql) — same
        atomic-claim pattern as synon_scheduler, to avoid two
        simultaneous issuances grabbing the same pooled key.
        """
        result = self._client.rpc(
            "claim_pool_key",
            {"p_table": self._pool_table, "p_product": product},
        ).execute()
        if not result.data:
            return None
        return result.data[0]["key"]

    def pool_remaining(self, product: str) -> int:
        result = (
            self._client.table(self._pool_table)
            .select("id", count="exact")
            .eq("product", product)
            .eq("assigned", False)
            .execute()
        )
        return result.count or 0

    # ------------------------------------------------------------------
    # Issuance
    # ------------------------------------------------------------------

    def issue_license(
        self,
        product: str,
        source: LicenseSource = LicenseSource.ON_DEMAND,
        customer_email: Optional[str] = None,
        bind_machine_id: Optional[str] = None,
    ) -> LicenseKey:
        """
        Issue a new license. `source` determines where the key comes
        from:
          - POOL: pulls an unassigned key from the pool. Raises if the
            pool is empty — caller decides what to do (alert you to
            top up the pool, fall back to on-demand, etc.)
          - ON_DEMAND: generates a fresh key, retrying on the rare
            collision (unique constraint on `key` column).
        """
        if source == LicenseSource.POOL:
            key_string = self._pull_from_pool(product)
            if key_string is None:
                raise RuntimeError(
                    f"synon_licensing: pool for product '{product}' is empty"
                )
        else:
            key_string = self._generate_unique_key()

        license_key = LicenseKey(
            key=key_string,
            product=product,
            source=source,
            customer_email=customer_email,
            bound_machine_id=bind_machine_id,
        )
        result = self._client.table(self._keys_table).insert(license_key.to_row()).execute()
        license_key.id = result.data[0]["id"]
        return license_key

    def _generate_unique_key(self, max_attempts: int = 5) -> str:
        for _ in range(max_attempts):
            candidate = generate_key_string()
            existing = (
                self._client.table(self._keys_table)
                .select("id")
                .eq("key", candidate)
                .limit(1)
                .execute()
            )
            if not existing.data:
                return candidate
        raise RuntimeError("synon_licensing: failed to generate a unique key after retries")

    # ------------------------------------------------------------------
    # Lookup / validation support
    # ------------------------------------------------------------------

    def get_license(self, key: str) -> Optional[LicenseKey]:
        result = (
            self._client.table(self._keys_table)
            .select("*")
            .eq("key", key)
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
        return LicenseKey.from_row(result.data[0])

    def get_trial_usage(self, license_key_id: str) -> Optional[TrialUsage]:
        result = (
            self._client.table(self._trial_table)
            .select("*")
            .eq("license_key_id", license_key_id)
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
        return TrialUsage.from_row(result.data[0])

    def start_trial(
        self, license_key_id: str, max_days: Optional[int], max_runs: Optional[int]
    ) -> TrialUsage:
        trial = TrialUsage(license_key_id=license_key_id, max_days=max_days, max_runs=max_runs)
        result = self._client.table(self._trial_table).insert(trial.to_row()).execute()
        trial.id = result.data[0]["id"]
        return trial

    def increment_run_count(self, trial: TrialUsage) -> None:
        trial.run_count += 1
        self._client.table(self._trial_table).update(
            {"run_count": trial.run_count}
        ).eq("id", trial.id).execute()

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def bind_machine(self, license_key: LicenseKey, machine_id: str) -> None:
        license_key.bound_machine_id = machine_id
        self._client.table(self._keys_table).update(
            {"bound_machine_id": machine_id}
        ).eq("id", license_key.id).execute()

    def revoke(self, license_key: LicenseKey) -> None:
        license_key.status = LicenseStatus.REVOKED
        license_key.revoked_at = datetime.now(timezone.utc)
        self._client.table(self._keys_table).update(
            {"status": license_key.status.value, "revoked_at": license_key.revoked_at.isoformat()}
        ).eq("id", license_key.id).execute()
