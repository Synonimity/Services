"""
Unlike the original standalone service, this doesn't load its own .env.
The host app builds this from wherever it already gets its config (its
own settings object, the Env/Secrets service, plain os.environ, whatever)
and hands it to NotificationsService.
"""
from pydantic import BaseModel


class NotificationsConfig(BaseModel):
    resend_api_key: str
    resend_webhook_secret: str = ""
    email_from_address: str
    email_from_name: str = ""

    brand_name: str = "Your App"
    brand_color: str = "#FF6A00"
    brand_logo_url: str = ""
    brand_footer_text: str = ""

    slack_webhook_url: str = ""
    discord_webhook_url: str = ""

    @property
    def from_header(self) -> str:
        return f"{self.email_from_name} <{self.email_from_address}>" if self.email_from_name else self.email_from_address
