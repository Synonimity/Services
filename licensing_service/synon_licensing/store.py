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

from .config import LicensingConfig
from .keygen import generate_key_string
from .models import LicenseKey, LicenseSource, LicenseStatus, TrialUsage


class LicensingStore:
    def __init__(self, config: LicensingConfig, client: Optional[Client] = None):
        self.config = config
        if client is not None:
            self._client = client
        else:
            self._client = create_client(
                config.supabase_url, config.supabase_service_role_key
            )
        self._keys_table = config.license_keys_table
        self._pool_table = config.license_key_pool_table
        self._trial_table = config.trial_usage_table

    # ------------------------------------------------------------------
    # Pool management
    # ------------------------------------------------------------------

    def add_to_pool(self, product: str, count: int) -> int:
        """
        Pre-generate `count` unassigned keys for `product` and insert
        into the pool table. Returns the number actually inserted.
        """
        rows = []
        for _ in range(count):
            rows.append({
                "key": generate_key_string(
                    self.config.license_key_segment_length,
                    self.config.license_key_segment_count
                ),
                "product": product,
                "assigned": False
            })

        # Insert one at a time so a single collision doesn't fail the batch
        inserted = 0
        for row in rows:
            try:
                self._client.table(self._pool_table).insert(row).execute()
                inserted += 1
            except Exception:
                continue
        return inserted

    def _pull_from_pool(self, product: str) -> Optional[str]:
        """
        Atomically claims one unassigned key from the pool via the
        `claim_pool_key` Postgres function (see schema.sql).
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
        max_attempts: int = 5,
    ) -> LicenseKey:
        """
        Issue a new license.
        """
        for _ in range(max_attempts):
            if source == LicenseSource.POOL:
                key_string = self._pull_from_pool(product)
                if key_string is None:
                    raise RuntimeError(
                        f"synon_licensing: pool for product '{product}' is empty"
                    )
            else:
                key_string = generate_key_string(
                    self.config.license_key_segment_length,
                    self.config.license_key_segment_count
                )

            license_key = LicenseKey(
                key=key_string,
                product=product,
                source=source,
                customer_email=customer_email,
                bound_machine_id=bind_machine_id,
            )
            try:
                result = self._client.table(self._keys_table).insert(license_key.to_row()).execute()
                license_key.id = result.data[0]["id"]
                return license_key
            except Exception:
                if source == LicenseSource.POOL:
                    # If pool claim succeeded but issuance failed (unlikely unique collision
                    # with historical data), we effectively lost a pooled key.
                    # This is rare enough to just raise or continue.
                    raise
                continue

        raise RuntimeError("synon_licensing: failed to issue unique license after retries")

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

    def increment_run_count(self, trial_id: str) -> None:
        """Atomic run count increment."""
        # Supabase Python client doesn't support atomic increment easily without RPC
        # unless we use a raw query or another RPC.
        # But we can use the .update() with a PostgreSQL-style increment if supported?
        # Actually, best practice in Supabase is an RPC or just accepting the race
        # if using the simple client. The audit suggested atomic SQL update.
        # Let's use the .rpc() pattern if we want to be truly atomic, or a direct
        # Supabase 'increment' if the library supports it.
        # supabase-py doesn't have a direct 'increment'.
        # I'll add an RPC to schema.sql for this.
        self._client.rpc("increment_trial_runs", {"p_trial_id": trial_id}).execute()

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
