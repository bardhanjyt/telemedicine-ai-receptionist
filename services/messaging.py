import logging
import os
import re
from typing import Optional
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from receptionist_agent import ReceptionistAgent, GuestInfo
from urllib.parse import urlparse, urljoin

# Configure logging for error tracking and debugging
logging.basicConfig(
    filename='messaging.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Securely load Twilio credentials from environment variables
TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "****")

# Validate Twilio configuration
if not all([TWILIO_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER]):
    logging.error("Missing Twilio configuration: TWILIO_SID, TWILIO_AUTH_TOKEN, or TWILIO_FROM_NUMBER")
    raise ValueError("Missing Twilio configuration")

# Initialize receptionist agent for phone number validation
try:
    receptionist = ReceptionistAgent()
    logging.info("ReceptionistAgent initialized in messaging")
except Exception as e:
    logging.error(f"Failed to initialize ReceptionistAgent: {str(e)}")
    raise

def _sanitize_input(input_str: str) -> str:
    """
    Sanitize input to prevent injection attacks
    
    Args:
        input_str (str): Input string to sanitize
    
    Returns:
        str: Sanitized string
    """
    if not input_str:
        return ""
    # Remove dangerous characters and trim whitespace
    return re.sub(r'[<>;{}]', '', input_str.strip())

def _sanitize_url(url: str) -> Optional[str]:
    """
    Sanitize and validate a URL to ensure it is safe
    
    Args:
        url (str): URL to sanitize
    
    Returns:
        Optional[str]: Sanitized URL or None if invalid
    """
    try:
        # Parse and validate URL
        parsed = urlparse(url)
        if not parsed.scheme in ('http', 'https') or not parsed.netloc:
            logging.warning(f"Invalid URL: {url}")
            return None
        # Reconstruct URL to ensure safety
        safe_url = urljoin(f"{parsed.scheme}://{parsed.netloc}", parsed.path)
        return safe_url
    except Exception as e:
        logging.error(f"Error sanitizing URL {url}: {str(e)}")
        return None

def send_confirmation_sms(to_number: str, doctor: str, time: str, calendly_link: str) -> bool:
    """
    Send a confirmation SMS for an appointment using Twilio
    
    Args:
        to_number (str): Recipient's phone number
        doctor (str): Name of the doctor
        time (str): Appointment time
        calendly_link (str): Calendly booking URL
    
    Returns:
        bool: True if the SMS was sent successfully, False otherwise
    """
    try:
        # Sanitize inputs
        to_number = _sanitize_input(to_number)
        doctor = _sanitize_input(doctor)
        time = _sanitize_input(time)
        calendly_link = _sanitize_url(calendly_link)
        
        if not all([to_number, doctor, time, calendly_link]):
            logging.warning("Missing required parameters for SMS")
            return False

        # Validate phone number using ReceptionistAgent
        guest_data = {
            "name": "Guest",  # Placeholder, as name is not critical for SMS
            "email": "guest@example.com",  # Placeholder
            "phone": to_number,
            "purpose": f"Appointment confirmation with {doctor} at {time}"
        }
        validated_guest = receptionist.validate_input(guest_data)
        if not validated_guest:
            logging.error(f"Invalid phone number: {to_number}")
            return False

        # Initialize Twilio client
        client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)
        
        # Construct message body
        body = f"Your appointment with Dr. {doctor} is confirmed for {time}. Details: {calendly_link}"
        if len(body) > 1600:  # Twilio SMS limit
            logging.warning("SMS body exceeds 1600 characters")
            body = body[:1597] + "..."  # Truncate safely

        # Send SMS
        message = client.messages.create(
            body=body,
            from_=TWILIO_FROM_NUMBER,
            to=validated_guest.phone
        )

        logging.info(f"SMS sent successfully to {to_number} for appointment with {doctor} at {time}. Message SID: {message.sid}")
        return True
    except TwilioRestException as e:
        logging.error(f"Twilio API error sending SMS to {to_number}: {str(e)}")
        return False
    except Exception as e:
        logging.error(f"Error sending SMS to {to_number}: {str(e)}")
        return False