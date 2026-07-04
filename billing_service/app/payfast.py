"""
All PayFast-specific logic lives here.

PayFast's official documentation site (developers.payfast.co.za) is fully
JS-rendered and I could not scrape its exact field-order rules directly.
The checkout/ITN signature algorithm below is built from PayFast's
published field list combined with a documented, widely-used fix for a bug
in PayFast's own sample code (their sample replaces spaces incorrectly and
doesn't sort fields into the right order, which breaks the signature).
Source for the fix: https://www.deanmalan.co.za/2023/2023-02-08-calculate-payfast-signature.html

The Subscriptions management API (pause/cancel/etc, app.payfast_api below)
is less consistently documented across PayFast's own sources. VERIFY THIS
SECTION AGAINST YOUR OWN SANDBOX ACCOUNT before relying on it in
production - test every action (fetch/pause/unpause/cancel/update/adhoc)
with a real sandbox subscription token first.
"""
import socket
from datetime import datetime, timezone
from hashlib import md5
from urllib.parse import quote_plus

import httpx

from app.config import get_settings

settings = get_settings()

# Exact field order PayFast expects when calculating the checkout/ITN
# signature - order matters, this is NOT alphabetical.
SIGNATURE_FIELD_ORDER = [
    "merchant_id",
    "merchant_key",
    "return_url",
    "cancel_url",
    "notify_url",
    "name_first",
    "name_last",
    "email_address",
    "cell_number",
    "m_payment_id",
    "amount",
    "item_name",
    "item_description",
    "custom_int1",
    "custom_int2",
    "custom_int3",
    "custom_int4",
    "custom_int5",
    "custom_str1",
    "custom_str2",
    "custom_str3",
    "custom_str4",
    "custom_str5",
    "email_confirmation",
    "confirmation_address",
    "payment_method",
    "subscription_type",
    "billing_date",
    "recurring_amount",
    "frequency",
    "cycles",
    # Fields PayFast adds to the ITN payload that aren't part of the
    # outbound checkout form, but still need to be in the signature when
    # validating an inbound ITN - appended at the end, which matches the
    # order PayFast sends them in.
    "pf_payment_id",
    "payment_status",
    "amount_gross",
    "amount_fee",
    "amount_net",
    "amount_blocked",
]

VALID_PAYFAST_HOSTS = {
    "www.payfast.co.za",
    "sandbox.payfast.co.za",
    "w1w.payfast.co.za",
    "w2w.payfast.co.za",
}


def _ordered_items(data: dict[str, str]) -> list[tuple[str, str]]:
    """Drop blanks, trim whitespace, and order by PayFast's expected field order."""
    cleaned = {k: str(v).strip() for k, v in data.items() if v is not None and str(v).strip() != "" and k != "signature"}
    priority = {k: i for i, k in enumerate(SIGNATURE_FIELD_ORDER)}
    ordered_keys = sorted(cleaned.keys(), key=lambda k: priority.get(k, len(SIGNATURE_FIELD_ORDER)))
    return [(k, cleaned[k]) for k in ordered_keys]


def calculate_signature(data: dict[str, str]) -> str:
    pairs = _ordered_items(data)
    param_string = "&".join(f"{k}={quote_plus(v)}" for k, v in pairs)
    if settings.payfast_passphrase:
        param_string += f"&passphrase={quote_plus(settings.payfast_passphrase)}"
    return md5(param_string.encode()).hexdigest()


def build_checkout_payload(
    *,
    m_payment_id: str,
    amount: float,
    item_name: str,
    email: str,
    name_first: str | None,
    name_last: str | None,
    recurring_amount: float | None = None,
    frequency: int | None = None,
    cycles: int | None = None,
) -> dict[str, str]:
    """
    Builds the signed field set for a checkout form. `amount` is what's
    charged today (the first payment); recurring_amount/frequency/cycles
    set up the subscription for future charges. For a plain once-off
    payment, just omit the recurring_* args.
    """
    data: dict[str, str] = {
        "merchant_id": settings.payfast_merchant_id,
        "merchant_key": settings.payfast_merchant_key,
        "return_url": settings.payfast_return_url,
        "cancel_url": settings.payfast_cancel_url,
        "notify_url": f"{settings.base_url}/billing/itn",
        "email_address": email,
        "m_payment_id": m_payment_id,
        "amount": f"{amount:.2f}",
        "item_name": item_name,
    }
    if name_first:
        data["name_first"] = name_first
    if name_last:
        data["name_last"] = name_last

    if frequency is not None:
        data["subscription_type"] = "1"  # 1 = subscription, 2 = tokenization (ad-hoc)
        data["recurring_amount"] = f"{(recurring_amount if recurring_amount is not None else amount):.2f}"
        data["frequency"] = str(frequency)
        data["cycles"] = str(cycles if cycles is not None else 0)

    data["signature"] = calculate_signature(data)
    return data


def checkout_redirect_url(payload: dict[str, str]) -> str:
    query = "&".join(f"{k}={quote_plus(v)}" for k, v in payload.items())
    return f"{settings.payfast_base_url}/eng/process?{query}"


# ---------------------------------------------------------------------------
# ITN (Instant Transaction Notification) validation
# ---------------------------------------------------------------------------
def verify_itn_signature(data: dict[str, str]) -> bool:
    received = data.get("signature", "")
    expected = calculate_signature(data)
    return received.lower() == expected.lower()


def verify_source_host(client_ip: str) -> bool:
    """
    Best-effort check that the request actually came from PayFast, by
    reverse-resolving the IP and checking it against PayFast's known
    hostnames. PayFast's IP ranges have changed before (e.g. their 2025 AWS
    migration), so treat this as a secondary signal - the authoritative
    check is verify_with_payfast() below, which PayFast recommends doing
    for every ITN.
    """
    try:
        host, _, _ = socket.gethostbyaddr(client_ip)
    except (socket.herror, socket.gaierror):
        return False
    return host in VALID_PAYFAST_HOSTS


async def verify_with_payfast(data: dict[str, str]) -> bool:
    """Re-post the received ITN data back to PayFast; they confirm it's genuine."""
    url = f"{settings.payfast_base_url}/eng/query/validate"
    body = {k: v for k, v in data.items()}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    return resp.status_code == 200 and resp.text.strip() == "VALID"


# ---------------------------------------------------------------------------
# Subscriptions management API
# UNVERIFIED AGAINST LIVE PAYFAST DOCS - test thoroughly in sandbox first.
# ---------------------------------------------------------------------------
def _api_headers(extra_body: dict[str, str] | None = None) -> dict[str, str]:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    signing_data = dict(extra_body or {})
    signing_data.update(
        {
            "merchant-id": settings.payfast_merchant_id,
            "version": "v1",
            "timestamp": timestamp,
        }
    )
    if settings.payfast_passphrase:
        signing_data["passphrase"] = settings.payfast_passphrase

    param_string = "&".join(f"{k}={quote_plus(str(v))}" for k, v in sorted(signing_data.items()))
    signature = md5(param_string.encode()).hexdigest()

    return {
        "merchant-id": settings.payfast_merchant_id,
        "version": "v1",
        "timestamp": timestamp,
        "signature": signature,
    }


async def _api_request(method: str, path: str, body: dict[str, str] | None = None) -> httpx.Response:
    url = f"{settings.payfast_api_base_url}{path}"
    headers = _api_headers(body)
    async with httpx.AsyncClient(timeout=15) as client:
        return await client.request(method, url, data=body, headers=headers)


async def fetch_subscription(token: str) -> dict:
    resp = await _api_request("GET", f"/subscriptions/{token}/fetch")
    resp.raise_for_status()
    return resp.json()


async def pause_subscription(token: str, cycles: int = 1) -> dict:
    resp = await _api_request("PUT", f"/subscriptions/{token}/pause", {"cycles": str(cycles)})
    resp.raise_for_status()
    return resp.json()


async def unpause_subscription(token: str) -> dict:
    resp = await _api_request("PUT", f"/subscriptions/{token}/unpause")
    resp.raise_for_status()
    return resp.json()


async def cancel_subscription(token: str) -> dict:
    resp = await _api_request("PUT", f"/subscriptions/{token}/cancel")
    resp.raise_for_status()
    return resp.json()
