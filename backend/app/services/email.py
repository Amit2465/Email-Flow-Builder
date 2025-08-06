import os
import smtplib
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from itsdangerous import URLSafeTimedSerializer
from urllib.parse import quote
import logging

# Hardcoded secret key for signing tokens. Must match the key in api/tracking.py
SECRET_KEY = "your-super-secret-key-that-is-hardcoded"

# The public URL of the API, used for generating tracking links.
# Using the ngrok URL provided by the user - supports both HTTP and HTTPS
# ngrok automatically handles both HTTP and HTTPS requests to the same endpoint
API_PUBLIC_URL = "https://ce4bb4e597bb.ngrok-free.app"

# Fallback HTTP URL for compatibility (if HTTPS fails)
API_PUBLIC_URL_HTTP = "http://ce4bb4e597bb.ngrok-free.app"

def get_tracking_url(endpoint: str, token: str, **params) -> str:
    """Generate tracking URL with protocol fallback support for ngrok"""
    logger = logging.getLogger(__name__)
    try:
        # Build query parameters
        query_params = "&".join([f"{k}={quote(str(v), safe='')}" for k, v in params.items()])
        query_string = f"?token={token}&{query_params}" if params else f"?token={token}"
        
        # Use HTTPS as primary (ngrok supports both HTTP and HTTPS)
        tracking_url = f"{API_PUBLIC_URL}{endpoint}{query_string}"
        logger.debug(f"[EMAIL] Generated tracking URL: {tracking_url}")
        return tracking_url
    except Exception as e:
        logger.error(f"[EMAIL] Failed to generate tracking URL: {e}")
        # Fallback to HTTP if HTTPS fails
        fallback_url = f"{API_PUBLIC_URL_HTTP}{endpoint}{query_string}"
        logger.warning(f"[EMAIL] Using HTTP fallback: {fallback_url}")
        return fallback_url

# Initialize serializer for tokens
serializer = URLSafeTimedSerializer(SECRET_KEY)

def convert_text_to_html(plain_text: str, links: list, click_token: str = None) -> str:
    """
    Convert plain text email body to HTML and add configured links as clickable buttons with tracking URLs.
    """
    if not plain_text:
        return ""
    
    # Convert plain text to HTML (preserve line breaks)
    html_content = plain_text.replace('\n', '<br>')
    
    # Add links as clickable buttons if any are configured
    if links:
        html_content += '<br><br>'
        for link in links:
            text = link.get("text", "").strip()
            url = link.get("url", "").strip()
            if text and url:
                # Create tracking URL if token is provided
                if click_token:
                    tracking_url = get_tracking_url("/api/track/click", click_token, url=url)
                else:
                    tracking_url = url
                
                # Create a styled button for each link
                button_html = f'''
                <div style="margin: 20px 0;">
                    <a href="{tracking_url}" style="
                        display: inline-block;
                        background-color: #007bff;
                        color: white;
                        padding: 12px 24px;
                        text-decoration: none;
                        border-radius: 5px;
                        font-weight: bold;
                        font-size: 16px;
                        text-align: center;
                        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    ">{text}</a>
                </div>
                '''
                html_content += button_html
    
    return html_content

# SMTP credentials will be loaded from the environment, as they are sensitive.
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

def send_email_with_tracking(
    subject: str,
    body: str,
    recipient_email: str,
    lead_id: str,
    campaign_id: str,
    links: list = None,
):
    """
    Sends an HTML email with tracking pixel and link tracking.
    """
    logger = logging.getLogger(__name__)

    # Validate input parameters
    if not subject or not subject.strip():
        logger.error(f"[EMAIL] Missing subject for lead {lead_id}")
        raise ValueError("Email subject is required")
    
    if not body or not body.strip():
        logger.error(f"[EMAIL] Missing body for lead {lead_id}")
        raise ValueError("Email body is required")
    
    if not recipient_email or not recipient_email.strip():
        logger.error(f"[EMAIL] Missing recipient email for lead {lead_id}")
        raise ValueError("Recipient email is required")
    
    if not lead_id or not campaign_id:
        logger.error(f"[EMAIL] Missing lead_id or campaign_id")
        raise ValueError("Lead ID and Campaign ID are required")

    logger.info(f"[EMAIL] === EMAIL SENDING STARTED ===")
    logger.info(f"[EMAIL] Lead ID: {lead_id}")
    logger.info(f"[EMAIL] Campaign ID: {campaign_id}")
    logger.info(f"[EMAIL] Recipient: {recipient_email}")
    logger.info(f"[EMAIL] Subject: {subject}")

    if not SMTP_USERNAME or not SMTP_PASSWORD:
        error_msg = "Missing SMTP credentials in .env file"
        logger.error(f"[EMAIL] {error_msg}")
        logger.error(f"[EMAIL] SMTP_USERNAME: {'SET' if SMTP_USERNAME else 'MISSING'}")
        logger.error(f"[EMAIL] SMTP_PASSWORD: {'SET' if SMTP_PASSWORD else 'MISSING'}")
        raise EnvironmentError(error_msg)

    # Generate tokens for both open and click tracking
    open_token = serializer.dumps({"lead_id": lead_id, "campaign_id": campaign_id, "type": "open"})
    click_token = serializer.dumps({"lead_id": lead_id, "campaign_id": campaign_id, "type": "click"})
    
    logger.info(f"[EMAIL] Generated tracking tokens for lead {lead_id}:")
    logger.info(f"[EMAIL] Open token: {open_token[:50]}...")
    logger.info(f"[EMAIL] Click token: {click_token[:50]}...")
    
    # Replace all links with tracking URLs
    def replace_links(html_content):
        if not html_content:
            logger.warning(f"[EMAIL] Empty HTML content for lead {lead_id}")
            return html_content
            
        # Find all href attributes
        link_pattern = r'href=["\']([^"\']+)["\']'
        
        def replace_link(match):
            original_url = match.group(1)
            
            # Skip if already a tracking URL
            if '/api/track/' in original_url:
                logger.debug(f"[EMAIL] Skipping already tracked URL: {original_url}")
                return match.group(0)
            
            # Validate URL format
            if not original_url or not original_url.strip():
                logger.warning(f"[EMAIL] Empty URL found in email for lead {lead_id}")
                return match.group(0)
            
            # Create tracking URL with better security - supports both HTTP and HTTPS
            try:
                tracking_url = get_tracking_url("/api/track/click", click_token, url=original_url)
                logger.debug(f"[EMAIL] Replaced link: {original_url} -> {tracking_url}")
                return f'href="{tracking_url}"'
            except Exception as e:
                logger.error(f"[EMAIL] Failed to create tracking URL for {original_url}: {e}")
                return match.group(0)  # Return original if tracking fails
        
        try:
            result = re.sub(link_pattern, replace_link, html_content)
            logger.info(f"[EMAIL] Link replacement completed for lead {lead_id}")
            return result
        except Exception as e:
            logger.error(f"[EMAIL] Link replacement failed for lead {lead_id}: {e}")
            return html_content  # Return original content if replacement fails
    
    # Convert plain text body to HTML and add links with tracking URLs
    html_body = convert_text_to_html(body, links or [], click_token)
    
    # Replace any remaining links with tracking URLs (for any links in the original text)
    tracked_body = replace_links(html_body)
    
    # Generate tracking pixel URL with protocol support
    tracking_pixel_url = get_tracking_url("/api/track/open", open_token)
    logger.info(f"[EMAIL] Generated tracking pixel URL: {tracking_pixel_url}")
    
    full_html_body = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{subject}</title>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .email-container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background-color: #f8f9fa; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
            .content {{ padding: 20px; }}
            .footer {{ background-color: #f8f9fa; padding: 15px; text-align: center; font-size: 12px; color: #666; margin-top: 20px; }}
        </style>
    </head>
    <body>
        <div class="email-container">
            <div class="header">
                <h2 style="margin: 0; color: #007bff;">EmailBuilder Campaign</h2>
            </div>
            <div class="content">
                {tracked_body}
            </div>
            <div class="footer">
                <p>This email was sent by EmailBuilder. If you have any questions, please contact us.</p>
                <p>© 2024 EmailBuilder. All rights reserved.</p>
            </div>
        </div>
        <img src="{tracking_pixel_url}" width="1" height="1" style="display:none;" alt="" />
    </body>
    </html>
    """

    # Construct MIME message with proper headers
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"EmailBuilder <{SMTP_USERNAME}>"
    msg["To"] = recipient_email
    msg["Reply-To"] = SMTP_USERNAME
    msg["X-Mailer"] = "EmailBuilder/1.0"
    msg["X-Priority"] = "3"
    msg["X-MSMail-Priority"] = "Normal"
    msg["Importance"] = "normal"
    msg["MIME-Version"] = "1.0"
    msg["Content-Type"] = "text/html; charset=UTF-8"
    msg["List-Unsubscribe"] = f"<mailto:{SMTP_USERNAME}?subject=unsubscribe>"
    msg["Precedence"] = "bulk"
    msg.attach(MIMEText(full_html_body, "html"))

    try:
        logger.info(f"[EMAIL] Starting SMTP connection for lead {lead_id}")
        smtp_server = "smtp.gmail.com"
        smtp_port = 587
        
        logger.debug(f"[EMAIL] Connecting to {smtp_server}:{smtp_port}")
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            logger.debug(f"[EMAIL] Connected to SMTP server {smtp_server}:{smtp_port}")
            server.starttls()
            logger.debug(f"[EMAIL] TLS started")
            
            logger.debug(f"[EMAIL] Authenticating with SMTP server")
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            logger.debug(f"[EMAIL] SMTP authentication successful")
            
            logger.debug(f"[EMAIL] Sending message to SMTP server")
            server.send_message(msg)
            logger.debug(f"[EMAIL] Message sent to SMTP server")
            
        logger.info(f"[EMAIL] === EMAIL SENT SUCCESSFULLY ===")
        logger.info(f"[EMAIL] Recipient: {recipient_email}")
        logger.info(f"[EMAIL] Lead ID: {lead_id}")
        logger.info(f"[EMAIL] Campaign ID: {campaign_id}")
        
    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"[EMAIL] SMTP Authentication failed for lead {lead_id}: {e}")
        logger.error(f"[EMAIL] Please check SMTP_USERNAME and SMTP_PASSWORD in .env file")
        raise
    except smtplib.SMTPRecipientsRefused as e:
        logger.error(f"[EMAIL] SMTP Recipients refused for lead {lead_id}: {e}")
        raise
    except smtplib.SMTPServerDisconnected as e:
        logger.error(f"[EMAIL] SMTP Server disconnected for lead {lead_id}: {e}")
        raise
    except smtplib.SMTPException as e:
        logger.error(f"[EMAIL] SMTP Exception for lead {lead_id}: {e}")
        raise
    except Exception as e:
        logger.error(f"[EMAIL] Failed to send email to {recipient_email} for lead {lead_id}: {e}", exc_info=True)
        raise
