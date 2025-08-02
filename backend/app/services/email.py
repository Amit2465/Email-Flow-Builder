import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv

# Load .env file
load_dotenv()

SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")


def send_email_with_tracking(
    subject: str,
    body: str,
    recipient_email: str,
    lead_id: str,
    campaign_id: str,
    tracking_url_base: str = "http://localhost:8000/api/track/open"
):
    """
    Sends an HTML email with a tracking pixel for open detection.

    Args:
        subject: Subject of the email.
        body: HTML body content (without tracking pixel).
        recipient_email: Receiver's email address.
        lead_id: Unique identifier of the lead.
        campaign_id: Campaign identifier.
        tracking_url_base: URL base of tracking endpoint.
    """
    import logging
    logger = logging.getLogger(__name__)

    logger.info("=" * 40)
    logger.info("=== EMAIL SENDING STARTED ===")
    logger.info(f"Recipient: {recipient_email}")
    logger.info(f"Subject: {subject}")
    logger.info(f"Lead ID: {lead_id}")
    logger.info(f"Campaign ID: {campaign_id}")
    logger.info("=" * 40)

    if not SMTP_USERNAME or not SMTP_PASSWORD:
        error_msg = "Missing SMTP credentials in .env file"
        logger.error(error_msg)
        raise EnvironmentError(error_msg)

    logger.info("SMTP credentials found, proceeding with email sending...")

    # Create full tracking pixel URL
    tracking_url = f"{tracking_url_base}?lead_id={lead_id}&campaign_id={campaign_id}"
    logger.info(f"Tracking URL created: {tracking_url}")

    # Build full HTML body with tracking pixel
    full_html_body = f"""
    <html>
      <body>
        {body}
        <img src="{tracking_url}" width="1" height="1" style="display:none;" alt="tracking-pixel" />
      </body>
    </html>
    """
    logger.info("HTML body with tracking pixel created")

    # Construct MIME message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_USERNAME
    msg["To"] = recipient_email
    msg.attach(MIMEText(full_html_body, "html"))
    logger.info("MIME message constructed")

    try:
        smtp_server = "smtp.gmail.com"
        smtp_port = 587

        logger.info(f"Connecting to SMTP server: {smtp_server}:{smtp_port}")
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            logger.info("SMTP connection established")
            server.starttls()
            logger.info("STARTTLS enabled")
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            logger.info("SMTP authentication successful")
            server.send_message(msg)
            logger.info("Email message sent successfully")

        logger.info("=" * 40)
        logger.info("=== EMAIL SENDING COMPLETED ===")
        logger.info(f"Email sent successfully to {recipient_email}")
        logger.info("=" * 40)
        
    except Exception as e:
        logger.error("=" * 40)
        logger.error("=== EMAIL SENDING FAILED ===")
        logger.error(f"Failed to send email to {recipient_email}: {e}")
        logger.error("=" * 40)
        raise
