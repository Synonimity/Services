from pydantic import BaseModel


class BillingConfig(BaseModel):
    payfast_merchant_id: str
    payfast_merchant_key: str
    payfast_passphrase: str = ""
    payfast_mode: str = "sandbox"  # "sandbox" | "live"

    # These are pages on the HOST app, not on this module.
    payfast_return_url: str
    payfast_cancel_url: str

    # The host app's own public base URL - used to build the ITN notify_url.
    # e.g. "https://app.kerfsuite.com" → ITN goes to
    # "https://app.kerfsuite.com/billing/itn"
    base_url: str

    @property
    def payfast_base_url(self) -> str:
        return "https://www.payfast.co.za" if self.payfast_mode == "live" else "https://sandbox.payfast.co.za"

    @property
    def payfast_api_base_url(self) -> str:
        return "https://api.payfast.co.za"

    @property
    def itn_notify_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/billing/itn"
