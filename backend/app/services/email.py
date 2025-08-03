import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from itsdangerous import URLSafeTimedSerializer
import logging

# Hardcoded secret key for signing tokens. Must match the key in api/tracking.py
SECRET_KEY = "your-super-secret-key-that-is-hardcoded"

# The public URL of the API, used for generating tracking links.
# For local development, this works. For EC2, this needs to be the public IP.
API_PUBLIC_URL = "http://localhost:8000"

# Initialize serializer for tokens
serializer = URLSafeTimedSerializer(SECRET_KEY)

# SMTP credentials will be loaded from the environment, as they are sensitive.
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

def send_email_with_tracking(
    subject: str,
    body: str,
    recipient_email: str,
    lead_id: str,
    campaign_id: str,
):
    """
    Sends an HTML email with a signed tracking pixel URL.
    """
    logger = logging.getLogger(__name__)

    if not SMTP_USERNAME or not SMTP_PASSWORD:
        error_msg = "Missing SMTP credentials in .env file"
        logger.error(error_msg)
        raise EnvironmentError(error_msg)

    # Generate a unique, timed token for this specific email open
    token = serializer.dumps({"lead_id": lead_id, "campaign_id": campaign_id})
    
    # Create full tracking pixel URL with the token
    tracking_url = f"{API_PUBLIC_URL}/api/track/open?token={token}"
    logger.info(f"Generated secure tracking URL for lead {lead_id}")

    # Build full HTML body with tracking pixel
    full_html_body = f"""
    <html>
      <body>
        {body}
        <img src="{tracking_url}" width="1" height="1" style="display:none;" alt="" />
      </body>
    </html>
    """

    # Construct MIME message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_USERNAME
    msg["To"] = recipient_email
    msg.attach(MIMEText(full_html_body, "html"))

    try:
        smtp_server = "smtp.gmail.com"
        smtp_port = 587
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
        logger.info(f"Email sent successfully to {recipient_email} for lead {lead_id}")
    except Exception as e:
        logger.error(f"Failed to send email to {recipient_email}: {e}", exc_info=True)
        raise
