"""
synon_licensing.models

PascalCase data classes representing license + trial state.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class LicenseStatus(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


class LicenseSource(str, Enum):
    POOL = "pool"  # pulled from a pre-generated batch
    ON_DEMAND = "on_demand"  # generated at issuance time


class LicenseCheckResult(str, Enum):
    """
    The outcome of validate_license() — what the calling app should
    actually do, not just raw status. Kept separate from LicenseStatus
    because a license can be ACTIVE but still fail a check (e.g. trial
    expired, or bound to a different machine).
    """

    VALID = "valid"
    INVALID_KEY = "invalid_key"
    REVOKED = "revoked"
    EXPIRED = "expired"
    MACHINE_MISMATCH = "machine_mismatch"
    TRIAL_EXPIRED = "trial_expired"
    TRIAL_RUNS_EXHAUSTED = "trial_runs_exhausted"


@dataclass
class LicenseKey:
    """A single issued license key."""

    key: str
    product: str
    status: LicenseStatus = LicenseStatus.ACTIVE
    source: LicenseSource = LicenseSource.ON_DEMAND
    bound_machine_id: Optional[str] = None  # null = not yet bound, or binding disabled for this product
    customer_email: Optional[str] = None
    issued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    revoked_at: Optional[datetime] = None
    id: Optional[str] = None

    def to_row(self) -> dict:
        return {
            "key": self.key,
            "product": self.product,
            "status": self.status.value,
            "source": self.source.value,
            "bound_machine_id": self.bound_machine_id,
            "customer_email": self.customer_email,
            "issued_at": self.issued_at.isoformat(),
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
        }

    @classmethod
    def from_row(cls, row: dict) -> "LicenseKey":
        return cls(
            id=row.get("id"),
            key=row["key"],
            product=row["product"],
            status=LicenseStatus(row["status"]),
            source=LicenseSource(row["source"]),
            bound_machine_id=row.get("bound_machine_id"),
            customer_email=row.get("customer_email"),
            issued_at=_parse_dt(row.get("issued_at")) or datetime.now(timezone.utc),
            revoked_at=_parse_dt(row.get("revoked_at")),
        )


@dataclass
class TrialUsage:
    """
    Trial constraints + consumption for a license. Separate from
    LicenseKey so a key can outlive its trial — e.g. upgraded to paid,
    same key, this row just stops being checked.

    max_days / max_runs: either can be None to disable that limit
    (e.g. run-count-only trial sets max_days=None).
    """

    license_key_id: str
    max_days: Optional[int] = None
    max_runs: Optional[int] = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    run_count: int = 0
    id: Optional[str] = None

    def to_row(self) -> dict:
        return {
            "license_key_id": self.license_key_id,
            "max_days": self.max_days,
            "max_runs": self.max_runs,
            "started_at": self.started_at.isoformat(),
            "run_count": self.run_count,
        }

    @classmethod
    def from_row(cls, row: dict) -> "TrialUsage":
        return cls(
            id=row.get("id"),
            license_key_id=row["license_key_id"],
            max_days=row.get("max_days"),
            max_runs=row.get("max_runs"),
            started_at=_parse_dt(row.get("started_at")) or datetime.now(timezone.utc),
            run_count=row.get("run_count", 0),
        )

    def days_elapsed(self) -> int:
        return (datetime.now(timezone.utc) - self.started_at).days

    def is_time_expired(self) -> bool:
        if self.max_days is None:
            return False
        return self.days_elapsed() >= self.max_days

    def is_runs_exhausted(self) -> bool:
        if self.max_runs is None:
            return False
        return self.run_count >= self.max_runs


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value)
