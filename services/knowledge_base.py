import logging
import os
import re
from datetime import datetime, time
from typing import Dict, List, Optional
import PyPDF2
from receptionist_agent import ReceptionistAgent, GuestInfo

# Configure logging for error tracking and debugging
logging.basicConfig(
    filename='knowledge_base.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Initialize receptionist agent for doctor name validation
try:
    receptionist = ReceptionistAgent()
    logging.info("ReceptionistAgent initialized in knowledge_base")
except Exception as e:
    logging.error(f"Failed to initialize ReceptionistAgent: {str(e)}")
    raise

# Doctor availability storage
DOCTOR_AVAILABILITY: Dict[str, List[Dict]] = {}

def _sanitize_path(file_path: str) -> str:
    """
    Sanitize file path to prevent directory traversal attacks
    
    Args:
        file_path (str): File path to sanitize
    
    Returns:
        str: Sanitized file path
    """
    try:
        # Remove dangerous characters and normalize path
        sanitized = os.path.normpath(file_path).replace("..", "").replace("/", "").replace("\\", "")
        # Ensure the file is in a safe directory (e.g., 'pdfs/')
        safe_path = os.path.join("pdfs", sanitized)
        if not safe_path.endswith(".pdf"):
            logging.warning(f"Invalid file extension for {safe_path}")
            raise ValueError("File must be a PDF")
        return safe_path
    except Exception as e:
        logging.error(f"Error sanitizing file path {file_path}: {str(e)}")
        raise

def _sanitize_doctor_name(name: str) -> str:
    """
    Sanitize doctor name to prevent injection and ensure consistency
    
    Args:
        name (str): Doctor name to sanitize
    
    Returns:
        str: Sanitized doctor name
    """
    if not name:
        return ""
    # Remove dangerous characters and normalize
    return re.sub(r'[<>;{}]', '', name.strip().lower().replace(" ", "_"))

def _parse_time_range(time_str: str) -> Optional[Dict[str, time]]:
    """
    Parse a time range string into start and end times
    
    Args:
        time_str (str): Time range (e.g., "10 AM - 2 PM")
    
    Returns:
        Optional[Dict[str, time]]: Dictionary with start_time and end_time, or None if invalid
    """
    try:
        match = re.match(r'(\d{1,2}\s*(?:AM|PM))\s*-\s*(\d{1,2}\s*(?:AM|PM))', time_str, re.IGNORECASE)
        if not match:
            logging.warning(f"Invalid time range format: {time_str}")
            return None

        start_str, end_str = match.groups()
        start_time = datetime.strptime(start_str, "%I %p").time()
        end_time = datetime.strptime(end_str, "%I %p").time()
        return {"start_time": start_time, "end_time": end_time}
    except Exception as e:
        logging.error(f"Error parsing time range {time_str}: {str(e)}")
        return None

def extract_doctor_availability(pdf_path: str) -> bool:
    """
    Extract doctor availability from a PDF and store in DOCTOR_AVAILABILITY
    
    Args:
        pdf_path (str): Path to the PDF file
    
    Returns:
        bool: True if extraction is successful, False otherwise
    """
    try:
        safe_path = _sanitize_path(pdf_path)
        if not os.path.exists(safe_path):
            logging.error(f"PDF file not found: {safe_path}")
            return False

        with open(safe_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for page_num, page in enumerate(reader.pages):
                text = page.extract_text()
                if not text:
                    logging.warning(f"No text found on page {page_num + 1} of {safe_path}")
                    continue

                # Example format: "Dr. Patel, Cardiology, Monday 10 AM - 2 PM"
                lines = text.split('\n')
                for line in lines:
                    match = re.match(
                        r'(Dr\.\s*\w+),\s*(\w+),\s*(\w+)\s+(\d{1,2}\s*(?:AM|PM)\s*-\s*\d{1,2}\s*(?:AM|PM))',
                        line.strip(),
                        re.IGNORECASE
                    )
                    if match:
                        doctor_name, department, day, time_range = match.groups()
                        doctor_name = _sanitize_doctor_name(doctor_name)

                        # Validate doctor name using ReceptionistAgent
                        guest_data = {
                            "name": doctor_name.replace("_", " ").title(),
                            "email": f"{doctor_name}@example.com",  # Placeholder
                            "phone": "+1234567890",  # Placeholder
                            "purpose": "Doctor availability"
                        }
                        validated_doctor = receptionist.validate_input(guest_data)
                        if not validated_doctor:
                            logging.warning(f"Invalid doctor name: {doctor_name}")
                            continue

                        time_info = _parse_time_range(time_range)
                        if not time_info:
                            continue

                        # Store availability
                        availability = {
                            "department": department.lower(),
                            "day": day.lower(),
                            "start_time": time_info["start_time"],
                            "end_time": time_info["end_time"]
                        }
                        if doctor_name not in DOCTOR_AVAILABILITY:
                            DOCTOR_AVAILABILITY[doctor_name] = []
                        DOCTOR_AVAILABILITY[doctor_name].append(availability)
                        logging.info(f"Extracted availability for {doctor_name}: {availability}")

        logging.info(f"Successfully processed PDF: {safe_path}")
        return True
    except Exception as e:
        logging.error(f"Error extracting availability from {safe_path}: {str(e)}")
        return False

def is_doctor_available(doctor_name: str, time_text: str, department: str = "general") -> bool:
    """
    Check if a doctor is available at the specified time and department
    
    Args:
        doctor_name (str): Name of the doctor (e.g., "Dr. Patel")
        time_text (str): Time string (e.g., "Monday at 2 PM" or ISO format)
        department (str): Department (e.g., "cardiology")
    
    Returns:
        bool: True if the doctor is available, False otherwise
    """
    try:
        doctor_name = _sanitize_doctor_name(doctor_name)
        department = department.lower()
        if not doctor_name or doctor_name not in DOCTOR_AVAILABILITY:
            logging.warning(f"Doctor {doctor_name} not found in availability data")
            return False

        # Parse time_text
        try:
            target_time = datetime.strptime(time_text, "%Y-%m-%dT%H:%M:%S").time()
            day = datetime.strptime(time_text, "%Y-%m-%dT%H:%M:%S").strftime("%A").lower()
        except ValueError:
            # Fallback for natural language (e.g., "Monday at 2 PM")
            match = re.match(r'(\w+)\s+at\s+(\d{1,2}\s*(?:AM|PM))', time_text, re.IGNORECASE)
            if not match:
                logging.warning(f"Invalid time format: {time_text}")
                return False
            day, time_str = match.groups()
            target_time = datetime.strptime(time_str, "%I %p").time()

        # Check availability
        for availability in DOCTOR_AVAILABILITY.get(doctor_name, []):
            if (availability["department"] == department and
                availability["day"] == day and
                availability["start_time"] <= target_time <= availability["end_time"]):
                logging.info(f"Doctor {doctor_name} available at {time_text} for {department}")
                return True

        logging.info(f"Doctor {doctor_name} not available at {time_text} for {department}")
        return False
    except Exception as e:
        logging.error(f"Error checking availability for {doctor_name} at {time_text}: {str(e)}")
        return False# Extract doctor availability from PDF