"""
synon_licensing.validator

The core check: validate_license(). Called every time a product
starts up (or periodically) to decide "is this install allowed to
run, and why/why not".

Deliberately returns a structured result rather than raising for
expected outcomes (expired trial, wrong machine, etc.) — those are
business states, not exceptions. Only genuinely unexpected failures
(DB unreachable) should raise.
"""

from dataclasses import dataclass
from typing import Optional

from .models import LicenseCheckResult, LicenseKey, LicenseStatus, TrialUsage
from .store import LicensingStore


@dataclass
class ValidationOutcome:
    result: LicenseCheckResult
    license_key: Optional[LicenseKey] = None
    trial_usage: Optional[TrialUsage] = None

    @property
    def is_valid(self) -> bool:
        return self.result == LicenseCheckResult.VALID


def validate_license(
    store: LicensingStore,
    key: str,
    product: str,
    machine_id: Optional[str] = None,
    consume_run: bool = False,
) -> ValidationOutcome:
    """
    Validates a license key for a given product.

    Args:
        key: the (already-normalized — see keygen.normalize_key_input)
             key string to check
        product: the product this check is for — a key issued for
                 "kerfcut" should not validate against "kerfstock"
        machine_id: if provided and the license has a bound machine,
                    must match. If the license has no bound machine
                    yet and machine_id is provided, this function does
                    NOT auto-bind — call store.bind_machine() explicitly
                    after a successful first validation, so binding is
                    an intentional step, not a side effect of checking.
        consume_run: if True and this license has trial usage tracking,
                     increments the run count as part of this check.
                     Set False for a "just checking" call (e.g. a UI
                     status display) vs True for "the app is actually
                     starting a billable run".

    Returns:
        ValidationOutcome with a specific LicenseCheckResult so the
        calling app can show the right message (not just "invalid").
    """
    license_key = store.get_license(key)

    if license_key is None:
        return ValidationOutcome(result=LicenseCheckResult.INVALID_KEY)

    if license_key.product != product:
        # Deliberately same result as "doesn't exist" — don't leak
        # to a prober that the key is valid for a *different* product.
        return ValidationOutcome(result=LicenseCheckResult.INVALID_KEY)

    if license_key.status == LicenseStatus.REVOKED:
        return ValidationOutcome(result=LicenseCheckResult.REVOKED, license_key=license_key)

    if license_key.status == LicenseStatus.EXPIRED:
        return ValidationOutcome(result=LicenseCheckResult.EXPIRED, license_key=license_key)

    if (
        machine_id is not None
        and license_key.bound_machine_id is not None
        and license_key.bound_machine_id != machine_id
    ):
        return ValidationOutcome(result=LicenseCheckResult.MACHINE_MISMATCH, license_key=license_key)

    trial = store.get_trial_usage(license_key.id)

    if trial is not None:
        if trial.is_time_expired():
            return ValidationOutcome(
                result=LicenseCheckResult.TRIAL_EXPIRED, license_key=license_key, trial_usage=trial
            )
        if trial.is_runs_exhausted():
            return ValidationOutcome(
                result=LicenseCheckResult.TRIAL_RUNS_EXHAUSTED,
                license_key=license_key,
                trial_usage=trial,
            )
        if consume_run:
            store.increment_run_count(trial)

    return ValidationOutcome(
        result=LicenseCheckResult.VALID, license_key=license_key, trial_usage=trial
    )
