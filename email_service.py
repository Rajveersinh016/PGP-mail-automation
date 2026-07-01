"""
email_service.py — PGP Glass Intelligence Engine
Sends the daily report email via Gmail SMTP using Python stdlib only.
  - HTML body
  - Excel (.xlsx) attachment
  - Multiple recipients (comma-separated RECIPIENTS env var)
  - Proper email headers to improve deliverability and avoid spam
  - Returns True on success, False on failure
"""

import email.utils
import logging
import os
import smtplib
import ssl
from datetime import datetime, timezone
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

log = logging.getLogger(__name__)

SMTP_HOST = "smtp.gmail.com"


def send_email(html_body: str, excel_path: str, article_count: int) -> bool:
    """
    Send the daily intelligence report email.

    Args:
        html_body:     Rendered HTML email body string
        excel_path:    Absolute path to the Excel attachment file
        article_count: Number of articles in this report (used in subject line)

    Returns:
        True if email sent successfully to ALL recipients, False otherwise.
    """
    gmail_user = os.environ.get("GMAIL_USER", "").strip()
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    recipients_raw = os.environ.get("RECIPIENTS", "").strip()

    # ── Validate config ───────────────────────────────────────────────────
    if not gmail_user:
        log.error("  GMAIL_USER environment variable is not set.")
        return False
    if not gmail_pass:
        log.error("  GMAIL_APP_PASSWORD environment variable is not set.")
        return False
    if not recipients_raw:
        log.error("  RECIPIENTS environment variable is not set.")
        return False

    recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]
    if not recipients:
        log.error("  No valid email recipients found in RECIPIENTS env var.")
        return False

    log.info(f"  Sending to {len(recipients)} recipient(s): {', '.join(recipients)}")

    # ── Build message ─────────────────────────────────────────────────────
    now_utc = datetime.now(timezone.utc)
    report_date = now_utc.strftime("%B %d, %Y")

    # Use ASCII-safe subject (avoid em-dash and special unicode which triggers spam filters)
    subject = f"PGP Container Glass Weekly Intelligence Report | {report_date} | {article_count} New Updates"

    msg = MIMEMultipart("mixed")

    # Proper From header with display name
    msg["From"] = email.utils.formataddr(("PGP Container Glass Intelligence", gmail_user))

    # Set To and BCC properly — send to all recipients
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject

    # Critical anti-spam headers
    msg["Date"] = email.utils.formatdate(localtime=False)
    msg["Message-ID"] = email.utils.make_msgid(domain=gmail_user.split("@")[-1] if "@" in gmail_user else "pgpglass.com")
    msg["X-Mailer"] = "PGP Container Glass Intelligence Platform v4.0"
    msg["MIME-Version"] = "1.0"

    # List-Unsubscribe header (important for Gmail inbox placement)
    msg["List-Unsubscribe"] = f"<mailto:{gmail_user}?subject=unsubscribe>"
    msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

    # Precedence header — use "bulk" for newsletters, avoids "promotional" tab
    msg["Precedence"] = "list"
    msg["X-Report-Type"] = "Container Glass Industry Intelligence"

    # Alternative container for HTML body
    alt_part = MIMEMultipart("alternative")

    # Plain text fallback (important — emails without plain text version get spam-flagged)
    plain_text = (
        f"PGP Container Glass Intelligence Platform - Weekly Intelligence Report\n"
        f"{'=' * 60}\n\n"
        f"Date: {report_date}\n"
        f"New updates found: {article_count}\n\n"
        f"This report contains {article_count} new container glass industry developments\n"
        f"and strategic customer insights worldwide, ranked by importance.\n\n"
        f"Please view this email in an HTML-capable email client for the\n"
        f"full formatted report with article summaries and category breakdowns.\n\n"
        f"The Excel attachment contains complete data for all articles:\n"
        f"- All Articles sheet with full metadata\n"
        f"- Country-wise summary\n"
        f"- Category breakdown\n"
        f"- Source coverage statistics\n\n"
        f"{'=' * 60}\n"
        f"This report is automatically generated weekly.\n"
        f"Powered by PGP Glass Intelligence Engine.\n"
        f"To unsubscribe, reply with 'unsubscribe' in the subject line.\n"
    )
    alt_part.attach(MIMEText(plain_text, "plain", "utf-8"))
    alt_part.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(alt_part)

    # Attach Excel file
    if excel_path and Path(excel_path).exists():
        filename = Path(excel_path).name
        with open(excel_path, "rb") as f:
            attachment = MIMEBase(
                "application",
                "vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            attachment.set_payload(f.read())
        encoders.encode_base64(attachment)
        attachment.add_header("Content-Disposition", "attachment", filename=filename)
        attachment.add_header("Content-Type",
                              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                              name=filename)
        msg.attach(attachment)
        log.info(f"  Attached: {filename}")
    else:
        log.warning(f"  Excel file not found at {excel_path} — sending without attachment")

    # ── Send via SMTP ─────────────────────────────────────────────────────
    context = ssl.create_default_context()
    connected = False
    server = None

    # Try Port 587 (STARTTLS) first
    try:
        log.info(f"  Attempting connection via {SMTP_HOST}:587 (STARTTLS)...")
        server = smtplib.SMTP(SMTP_HOST, 587, timeout=60)
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
        connected = True
    except Exception as e587:
        log.warning(f"  Port 587 connection failed: {e587}")
        if server:
            try:
                server.quit()
            except Exception:
                pass
            server = None

    # Fallback to Port 465 (SSL) if Port 587 failed
    if not connected:
        try:
            log.info(f"  Attempting fallback connection via {SMTP_HOST}:465 (SSL)...")
            server = smtplib.SMTP_SSL(SMTP_HOST, 465, context=context, timeout=60)
            connected = True
        except Exception as e465:
            log.error(f"  Port 465 connection failed: {e465}")
            if server:
                try:
                    server.quit()
                except Exception:
                    pass
                server = None

    if not connected or not server:
        log.error("  Failed to connect to Gmail SMTP on both ports 587 and 465. Check internet/firewall.")
        return False

    try:
        with server:
            server.login(gmail_user, gmail_pass)
            # sendmail sends to ALL recipients even if email shows only To:
            server.sendmail(gmail_user, recipients, msg.as_bytes())
            log.info(f"  Email sent successfully to {len(recipients)} recipient(s): {', '.join(recipients)}")
        return True

    except smtplib.SMTPAuthenticationError:
        log.error(
            "  Gmail authentication failed.\n"
            "    -> Make sure GMAIL_APP_PASSWORD is a valid App Password (not your Gmail password).\n"
            "    -> Go to: Google Account -> Security -> 2-Step Verification -> App Passwords"
        )
        return False

    except smtplib.SMTPRecipientsRefused as e:
        log.error(f"  Recipients refused: {e}")
        return False

    except smtplib.SMTPException as e:
        log.error(f"  SMTP error: {e}")
        return False

    except Exception as e:
        log.error(f"  Unexpected error sending email: {e}")
        return False
