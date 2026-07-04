"""
All PayFast signature logic. Refactored from the standalone service:
config is now passed in explicitly rather than read from a global
settings object, so this works in any host app regardless of how that
app loads its own config.
"""
import hashlib
import socket
from hashlib import md5
from urllib.parse import quote_plus

import httpx

from .config import BillingConfig

VALID_PAYFAST_HOSTS = {
    "www.payfast.co.za",
    "sandbox.payfast.co.za",
    "w1w.payfast.co.za",
    "w2w.payfast.co.za",
}

SIGNATURE_FIELD_ORDER = [
    "merchant_id", "merchant_key", "return_url", "cancel_url", "notify_url",
    "name_first", "name_last", "email_address", "cell_number", "m_payment_id",
    "amount", "item_name", "item_description",
    "custom_int1", "custom_int2", "custom_int3", "custom_int4", "custom_int5",
    "custom_str1", "custom_str2", "custom_str3", "custom_str4", "custom_str5",
    "email_confirmation", "confirmation_address", "payment_method",
    "subscription_type", "billing_date", "recurring_amount", "frequency", "cycles",
    "pf_payment_id", "payment_status",
    "amount_gross", "amount_fee", "amount_net", "amount_blocked",
]


def _ordered_items(data: dict[str, str], passphrase: str) -> str:
    cleaned = {k: str(v).strip() for k, v in data.items() if v is not None and str(v).strip() != "" and k != "signature"}
    priority = {k: i for i, k in enumerate(SIGNATURE_FIELD_ORDER)}
    ordered = sorted(cleaned.keys(), key=lambda k: priority.get(k, len(SIGNATURE_FIELD_ORDER)))
    param_string = "&".join(f"{k}={quote_plus(cleaned[k])}" for k in ordered)
    if passphrase:
        param_string += f"&passphrase={quote_plus(passphrase)}"
    return param_string


def calculate_signature(data: dict[str, str], passphrase: str) -> str:
    return md5(_ordered_items(data, passphrase).encode()).hexdigest()


def build_checkout_payload(
    *,
    config: BillingConfig,
    m_payment_id: str,
    amount: float,
    item_name: str,
    email: str,
    name_first: str | None,
    name_last: str | None,
    frequency: int | None = None,
    cycles: int | None = None,
) -> dict[str, str]:
    data: dict[str, str] = {
        "merchant_id": config.payfast_merchant_id,
        "merchant_key": config.payfast_merchant_key,
        "return_url": config.payfast_return_url,
        "cancel_url": config.payfast_cancel_url,
        "notify_url": config.itn_notify_url,
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
        data["subscription_type"] = "1"
        data["recurring_amount"] = f"{amount:.2f}"
        data["frequency"] = str(frequency)
        data["cycles"] = str(cycles if cycles is not None else 0)

    data["signature"] = calculate_signature(data, config.payfast_passphrase)
    return data


def checkout_redirect_url(config: BillingConfig, payload: dict[str, str]) -> str:
    query = "&".join(f"{k}={quote_plus(v)}" for k, v in payload.items())
    return f"{config.payfast_base_url}/eng/process?{query}"


def verify_itn_signature(data: dict[str, str], passphrase: str) -> bool:
    received = data.get("signature", "")
    expected = calculate_signature(data, passphrase)
    return received.lower() == expected.lower()


def verify_source_host(client_ip: str) -> bool:
    try:
        host, _, _ = socket.gethostbyaddr(client_ip)
    except (socket.herror, socket.gaierror):
        return False
    return host in VALID_PAYFAST_HOSTS


async def verify_with_payfast(config: BillingConfig, data: dict[str, str]) -> bool:
    url = f"{config.payfast_base_url}/eng/query/validate"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    return resp.status_code == 200 and resp.text.strip() == "VALID"


async def cancel_subscription(config: BillingConfig, token: str) -> dict:
    resp = await _api_request(config, "PUT", f"/subscriptions/{token}/cancel")
    resp.raise_for_status()
    return resp.json()


async def pause_subscription(config: BillingConfig, token: str, cycles: int = 1) -> dict:
    resp = await _api_request(config, "PUT", f"/subscriptions/{token}/pause", {"cycles": str(cycles)})
    resp.raise_for_status()
    return resp.json()


async def unpause_subscription(config: BillingConfig, token: str) -> dict:
    resp = await _api_request(config, "PUT", f"/subscriptions/{token}/unpause")
    resp.raise_for_status()
    return resp.json()


async def _api_request(config: BillingConfig, method: str, path: str, body: dict | None = None) -> httpx.Response:
    import time
    from datetime import datetime, timezone

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    signing_data = dict(body or {})
    signing_data.update({"merchant-id": config.payfast_merchant_id, "version": "v1", "timestamp": timestamp})
    if config.payfast_passphrase:
        signing_data["passphrase"] = config.payfast_passphrase

    param_string = "&".join(f"{k}={quote_plus(str(v))}" for k, v in sorted(signing_data.items()))
    signature = md5(param_string.encode()).hexdigest()

    headers = {
        "merchant-id": config.payfast_merchant_id,
        "version": "v1",
        "timestamp": timestamp,
        "signature": signature,
    }
    url = f"{config.payfast_api_base_url}{path}"
    async with httpx.AsyncClient(timeout=15) as client:
        return await client.request(method, url, data=body, headers=headers)
