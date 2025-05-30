import logging
import os
import re
from datetime import datetime, timedelta
from typing import Dict, Optional
import requests
from pydantic import ValidationError
from receptionist_agent import ReceptionistAgent, GuestInfo

# Configure logging for error tracking and debugging
logging.basicConfig(
    filename='calendly.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Securely load Calendly API key from environment variable
CALENDLY_API_KEY = os.getenv("CALENDLY_TOKEN")
if not CALENDLY_API_KEY:
    logging.error("CALENDLY_TOKEN environment variable not set")
    raise ValueError("CALENDLY_TOKEN environment variable not set")

# Mapping of doctor + department to Calendly event type UUIDs
DOCTOR_EVENT_MAP = {
    #Hidden due to privacy concerns
}

# Initialize receptionist agent for user data validation
try:
    receptionist = ReceptionistAgent()
    logging.info("ReceptionistAgent initialized in calendly")
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
    # Remove potentially dangerous characters and trim whitespace
    return re.sub(r'[<>;{}]', '', input_str.strip().lower().replace(" ", "_"))

def _parse_datetime(time_text: str) -> Optional[datetime]:
    """
    Parse time_text into a datetime object
    
    Args:
        time_text (str): Time string (e.g., "Monday at 2 PM" or ISO format)
    
    Returns:
        Optional[datetime]: Parsed datetime or None if parsing fails
    """
    try:
        # Attempt to parse ISO format first
        try:
            return datetime.fromisoformat(time_text)
        except ValueError:
            # Fallback to parsing natural language (simplified example)
            # In production, use a robust parser like dateutil.parser
            time_text = time_text.lower()
            if " at " in time_text:
                day, time = time_text.split(" at ")
                hour = int(re.search(r'\d+', time).group())
                if "pm" in time and hour < 12:
                    hour += 12
                # Assume next occurrence of the day in 2025
                day_map = {
                    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                    "friday": 4, "saturday": 5, "sunday": 6
                }
                target_day = day_map.get(day.strip())
                if target_day is None:
                    raise ValueError(f"Invalid day: {day}")
                today = datetime.now()
                days_ahead = (target_day - today.weekday() + 7) % 7 or 7
                target_date = today + timedelta(days=days_ahead)
                return datetime(target_date.year, target_date.month, target_date.day, hour)
        return None
    except Exception as e:
        logging.error(f"Error parsing datetime: {str(e)}")
        return None

def is_time_available(doctor_name: str, time_text: str) -> bool:
    """
    Check if a time slot is available for the specified doctor
    
    Args:
        doctor_name (str): Name of the doctor (e.g., "Dr. Patel")
        time_text (str): Time string (e.g., "Monday at 2 PM" or ISO format)
    
    Returns:
        bool: True if the slot is available, False otherwise
    """
    try:
        doctor_name = _sanitize_input(doctor_name)
        if not doctor_name:
            logging.warning("No doctor name provided")
            return False

        start_time = _parse_datetime(time_text)
        if not start_time:
            logging.warning(f"Invalid time format: {time_text}")
            return False

        end_time = start_time + timedelta(minutes=30)  # Assume 30-minute slots

        headers = {
            "Authorization": f"Bearer {CALENDLY_API_KEY}",
            "Content-Type": "application/json"
        }

        # Use a default event type for availability check
        event_type_uuid = DOCTOR_EVENT_MAP.get((doctor_name, "general"), list(DOCTOR_EVENT_MAP.values())[0])
        url = "https://api.calendly.com/scheduled_events"
        response = requests.get(
            url,
            headers=headers,
            params={
                "event_type": f"https://api.calendly.com/event_types/{event_type_uuid}",
                "min_start_time": start_time.isoformat(),
                "max_start_time": end_time.isoformat()
            }
        )

        if response.status_code == 200:
            data = response.json()
            events = data.get("collection", [])
            is_available = not bool(events)  # Slot is available if no events exist
            logging.info(f"Time slot {time_text} for {doctor_name} is {'available' if is_available else 'unavailable'}")
            return is_available
        else:
            logging.error(f"Calendly API error checking availability: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logging.error(f"Error in is_time_available: {str(e)}")
        return False

def create_calendly_appointment(doctor_name: str, department: str, user_info: Dict, appointment_time: str) -> Optional[str]:
    """
    Create a Calendly appointment and return a scheduling link
    
    Args:
        doctor_name (str): Name of the doctor (e.g., "Dr. Patel")
        department (str): Department (e.g., "cardiology")
        user_info (Dict): User information with name and email
        appointment_time (str): Appointment time (e.g., "Monday at 2 PM" or ISO format)
    
    Returns:
        Optional[str]: Booking URL if successful, None otherwise
    """
    try:
        doctor_name = _sanitize_input(doctor_name)
        department = _sanitize_input(department)
        event_type_uuid = DOCTOR_EVENT_MAP.get((doctor_name, department))
        if not event_type_uuid:
            logging.error(f"No event type found for {doctor_name} in {department}")
            raise ValueError(f"No event type found for {doctor_name} in {department}")

        # Validate user info using ReceptionistAgent
        guest_data = {
            "name": _sanitize_input(user_info.get("name", "")),
            "email": user_info.get("email", ""),
            "phone": user_info.get("phone", "+1234567890"),  # Fallback phone if not provided
            "purpose": f"Appointment with {doctor_name} in {department} at {appointment_time}"
        }
        validated_guest = receptionist.validate_input(guest_data)
        if not validated_guest:
            logging.error("User data validation failed")
            raise ValueError("User data validation failed")

        start_time = _parse_datetime(appointment_time)
        if not start_time:
            logging.error(f"Invalid appointment time format: {appointment_time}")
            raise ValueError(f"Invalid appointment time format: {appointment_time}")

        end_time = start_time + timedelta(minutes=30)  # Assume 30-minute slots

        headers = {
            "Authorization": f"Bearer {CALENDLY_API_KEY}",
            "Content-Type": "application/json"
        }

        # Create a one-time scheduling link
        response = requests.post(
            "https://api.calendly.com/scheduling_links",
            headers=headers,
            json={
                "owner": f"https://api.calendly.com/event_types/{event_type_uuid}",
                "max_event_count": 1,
                "owner_type": "EventType",
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "invitees": [
                    {
                        "email": validated_guest.email,
                        "name": validated_guest.name
                    }
                ]
            }
        )

        if response.status_code == 201:
            data = response.json()
            booking_url = data["resource"]["booking_url"]
            logging.info(f"Created Calendly appointment for {validated_guest.name} with {doctor_name} at {start_time}")
            return booking_url
        else:
            logging.error(f"Calendly API error: {response.status_code} - {response.text}")
            raise Exception(f"Failed to create Calendly appointment: {response.text}")
    except Exception as e:
        logging.error(f"Error in create_calendly_appointment: {str(e)}")
        return None