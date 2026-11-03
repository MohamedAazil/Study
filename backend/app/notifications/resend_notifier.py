import resend

from app.notifications.base import EmailMessage


class ResendNotifier:
    def __init__(self, api_key: str, sender: str):
        resend.api_key = api_key
        self._sender = sender

    def send_email(self, message: EmailMessage) -> None:
        params: dict = {"from": self._sender, "to": [message.to], "subject": message.subject, "html": message.html}
        if message.text:
            params["text"] = message.text
        resend.Emails.send(params)
