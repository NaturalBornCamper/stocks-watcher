"""
Shared email helper for the watcher cron commands.

Moved out of apps/watcher/views/cron.py: it is a plain wrapper around Django's
send_mail and is used by both the fetch_prices and send_alerts commands.
"""
from django.core.mail import send_mail

from utils.helpers import getenv


# Sends a plain-text email with an HTML copy where newlines become <br>.
def send_email(to: str, subject: str, body: str):
    send_mail(
        subject,
        body,
        getenv("FROM_EMAIL"),
        [to],
        fail_silently=False,
        html_message=body.replace("\n", "<br>"),
    )