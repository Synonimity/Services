from typing import Optional

from .config import LicensingConfig
from .store import LicensingStore
from .models import LicenseKey, LicenseSource, LicenseCheckResult
from .validator import validate_license
from .keygen import normalize_key_input


class LicensingService:
    def __init__(self, config: LicensingConfig, store: Optional[LicensingStore] = None):
        self.config = config
        self.store = store or LicensingStore(config=config)

    def issue_license(
        self,
        product: str,
        source: LicenseSource = LicenseSource.ON_DEMAND,
        customer_email: Optional[str] = None,
        bind_machine_id: Optional[str] = None,
    ) -> LicenseKey:
        return self.store.issue_license(
            product=product,
            source=source,
            customer_email=customer_email,
            bind_machine_id=bind_machine_id,
        )

    def validate(
        self,
        key: str,
        product: str,
        machine_id: Optional[str] = None,
        consume_run: bool = False,
    ):
        """
        Validate a license key for a product, optionally checking machine
        binding and trial limits.
        """
        normalized = normalize_key_input(key)
        return validate_license(
            store=self.store,
            key=normalized,
            product=product,
            machine_id=machine_id,
            consume_run=consume_run,
        )

    def start_trial(
        self, license_key_id: str, max_days: Optional[int] = None, max_runs: Optional[int] = None
    ):
        return self.store.start_trial(license_key_id, max_days, max_runs)

    def bind_machine(self, license_key: LicenseKey, machine_id: str):
        return self.store.bind_machine(license_key, machine_id)
