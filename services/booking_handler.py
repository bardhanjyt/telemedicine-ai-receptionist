import logging
import re
from datetime import datetime
from typing import Dict, Optional
from flask import Response, request
from twilio.twiml.voice_response import VoiceResponse, Gather, Play
from pydantic import ValidationError
from services.calendly import is_time_available, create_calendly_appointment
from services.messaging import send_confirmation_sms
from receptionist_agent import ReceptionistAgent, GuestInfo
from elevenlabs import generate_audio  # Placeholder for ElevenLabs API

# Configure logging for error tracking and debugging
logging.basicConfig(
    filename='booking_handler.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Initialize receptionist agent for guest data validation
try:
    receptionist = ReceptionistAgent()
    logging.info("ReceptionistAgent initialized in booking_handler")
except Exception as e:
    logging.error(f"Failed to initialize ReceptionistAgent: {str(e)}")
    raise

# Secure session storage (in-memory for simplicity, consider Redis in production)
secure_session_data: Dict[str, Dict] = {}

# ElevenLabs voice configuration
ELEVENLABS_VOICE_ID = "3UFZ7Pkyx3hNTropzBlS"  # Abigail - Customer Support Agent
ELEVENLABS_MODEL = "eleven_multilingual_v2"

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
    return re.sub(r'[<>;{}]', '', input_str.strip())

def _generate_audio_url(text: str) -> str:
    """
    Generate audio URL using ElevenLabs API
    
    Args:
        text (str): Text to convert to speech
    
    Returns:
        str: URL of the generated audio file
    """
    try:
        # Placeholder for ElevenLabs API call
        audio_url = generate_audio(
            text=text,
            voice_id=ELEVENLABS_VOICE_ID,
            model=ELEVENLABS_MODEL,
            language='en'  
        )
        logging.info(f"Generated audio URL for text: {text[:50]}...")
        return audio_url
    except Exception as e:
        logging.error(f"Error generating audio with ElevenLabs: {str(e)}")
        raise

def handle_booking() -> Response:
    """
    Handle initial booking request via voice input
    
    Returns:
        Response: TwiML response for Twilio to process
    """
    try:
        response = VoiceResponse()
        audio_url = _generate_audio_url(
            "Please say the name of the doctor you want to book an appointment with after the beep."
        )
        response.append(Play(audio_url))
        gather = Gather(
            input='speech',
            speechModel='command_and_search',
            action='/capture-doctor-name',
            method="POST",
            timeout=5
        )
        response.append(gather)
        error_audio_url = _generate_audio_url("Sorry, I didn't get that. Let's try again.")
        response.append(Play(error_audio_url))
        response.redirect('/book-appointment')
        logging.info("Initiated booking process")
        return Response(str(response), mimetype='application/xml')
    except Exception as e:
        logging.error(f"Error in handle_booking: {str(e)}")
        response = VoiceResponse()
        error_audio_url = _generate_audio_url("An error occurred. Please try again later.")
        response.append(Play(error_audio_url))
        response.hangup()
        return Response(str(response), mimetype='application/xml')

def capture_doctor_name(request_obj) -> Response:
    """
    Capture and validate doctor's name from voice input
    
    Args:
        request_obj: Flask request object containing speech result
    
    Returns:
        Response: TwiML response for next step or error
    """
    try:
        call_sid = _sanitize_input(request_obj.form.get("CallSid", ""))
        if not call_sid:
            raise ValueError("Missing CallSid")
        
        doctor_name = _sanitize_input(request_obj.form.get("SpeechResult", ""))
        if not doctor_name:
            logging.warning("No doctor name provided")
            response = VoiceResponse()
            error_audio_url = _generate_audio_url("No doctor name provided. Please try again.")
            response.append(Play(error_audio_url))
            response.redirect('/book-appointment')
            return Response(str(response), mimetype='application/xml')

        secure_session_data[call_sid] = {"doctor": doctor_name}
        logging.info(f"Captured doctor name: {doctor_name} for CallSid: {call_sid}")

        response = VoiceResponse()
        response.append(Play(_generate_audio_url(f"Great. You said Doctor {doctor_name}.")))
        response.append(Play(_generate_audio_url(
            "Please say the date and time you'd like to book. For example, say Monday at 2 PM."
        )))
        gather = Gather(
            input='speech',
            speechModel='command_and_search',
            action='/capture-appointment-time',
            method="POST",
            timeout=5
        )
        response.append(gather)
        response.append(Play(_generate_audio_url("Sorry, I didn't catch that.")))
        response.redirect('/book-appointment')
        return Response(str(response), mimetype='application/xml')
    except Exception as e:
        logging.error(f"Error in capture_doctor_name: {str(e)}")
        response = VoiceResponse()
        response.append(Play(_generate_audio_url("An error occurred. Please try again.")))
        response.redirect('/book-appointment')
        return Response(str(response), mimetype='application/xml')

def capture_appointment_time(request_obj) -> Response:
    """
    Capture and validate appointment time, check availability
    
    Args:
        request_obj: Flask request object containing speech result
    
    Returns:
        Response: TwiML response for next step or error
    """
    try:
        call_sid = _sanitize_input(request_obj.form.get("CallSid", ""))
        time_text = _sanitize_input(request_obj.form.get("SpeechResult", ""))
        
        if not call_sid or call_sid not in secure_session_data:
            raise ValueError("Invalid or missing CallSid")
        if not time_text:
            raise ValueError("No appointment time provided")

        session = secure_session_data[call_sid]
        session["time_text"] = time_text
        secure_session_data[call_sid] = session
        logging.info(f"Captured appointment time: {time_text} for CallSid: {call_sid}")

        if not is_time_available(session["doctor"], time_text):
            logging.warning(f"Time {time_text} not available for Dr. {session['doctor']}")
            response = VoiceResponse()
            response.append(Play(_generate_audio_url(
                f"I'm sorry, Dr. {session['doctor']} is not available at {time_text}."
            )))
            response.append(Play(_generate_audio_url("Please say a different date and time.")))
            gather = Gather(
                input='speech',
                speechModel='command_and_search',
                    action='/capture-appointment-time',
                method="POST",
                timeout=5
            )
            response.append(gather)
            return Response(str(response), mimetype='application/xml')

        response = VoiceResponse()
        response.append(Play(_generate_audio_url(
            f"Dr. {session['doctor']} is available at {time_text}."
        )))
        response.append(Play(_generate_audio_url("Please say your full name.")))
        gather = Gather(
            input='speech',
            speechModel='command_and_search',
            action='/capture-user-name',
            method="POST",
            timeout=5
        )
        response.append(gather)
        logging.info(f"Proceeding to capture user name for CallSid: {call_sid}")
        return Response(str(response), mimetype='application/xml')
    except Exception as e:
        logging.error(f"Error in capture_appointment_time: {str(e)}")
        response = VoiceResponse()
        response.append(Play(_generate_audio_url("An error occurred. Please try again.")))
        response.redirect('/book-appointment')
        return Response(str(response), mimetype='application/xml')

def capture_user_name(request_obj) -> Response:
    """
    Capture and validate user's name
    
    Args:
        request_obj: Flask request object containing speech result
    
    Returns:
        Response: TwiML response for next step or error
    """
    try:
        call_sid = _sanitize_input(request_obj.form.get("CallSid", ""))
        name = _sanitize_input(request_obj.form.get("SpeechResult", ""))
        
        if not call_sid or call_sid not in secure_session_data:
            raise ValueError("Invalid or missing CallSid")
        if not name:
            raise ValueError("No name provided")

        secure_session_data[call_sid]["name"] = name
        logging.info(f"Captured user name: {name} for CallSid: {call_sid}")

        response = VoiceResponse()
        response.append(Play(_generate_audio_url(
            "Thanks. Now say your mobile number digit by digit."
        )))
        gather = Gather(
            input='speech',
            speechModel='command_and_search',
            action='/capture-user-phone',
            method="POST",
            timeout=5
        )
        response.append(gather)
        return Response(str(response), mimetype='application/xml')
    except Exception as e:
        logging.error(f"Error in capture_user_name: {str(e)}")
        response = VoiceResponse()
        response.append(Play(_generate_audio_url("An error occurred. Please try again.")))
        response.redirect('/book-appointment')
        return Response(str(response), mimetype='application/xml')

def capture_user_phone(request_obj) -> Response:
    """
    Capture and validate user's phone number
    
    Args:
        request_obj: Flask request object containing speech result
    
    Returns:
        Response: TwiML response for next step or error
    """
    try:
        call_sid = _sanitize_input(request_obj.form.get("CallSid", ""))
        phone = _sanitize_input(request_obj.form.get("SpeechResult", "")).replace(" ", "").replace("-", "")
        
        if not call_sid or call_sid not in secure_session_data:
            raise ValueError("Invalid or missing CallSid")
        if not phone or not re.match(r'^\+?[1-9]\d{1,14}$', phone):
            raise ValueError("Invalid phone number format")

        secure_session_data[call_sid]["phone"] = phone
        logging.info(f"Captured phone number: {phone} for CallSid: {call_sid}")

        response = VoiceResponse()
        response.append(Play(_generate_audio_url("Please say your address.")))
        gather = Gather(
            input='speech',
            speechModel='command_and_search',
            action='/capture-user-address',
            method="POST",
            timeout=5
        )
        response.append(gather)
        return Response(str(response), mimetype='application/xml')
    except Exception as e:
        logging.error(f"Error in capture_user_phone: {str(e)}")
        response = VoiceResponse()
        response.append(Play(_generate_audio_url("An error occurred. Please try again.")))
        response.redirect('/book-appointment')
        return Response(str(response), mimetype='application/xml')

def capture_user_address(request_obj) -> Response:
    """
    Capture user address, validate all data, and book appointment
    
    Args:
        request_obj: Flask request object containing speech result
    
    Returns:
        Response: TwiML response with booking confirmation or error
    """
    try:
        call_sid = _sanitize_input(request_obj.form.get("CallSid", ""))
        address = _sanitize_input(request_obj.form.get("SpeechResult", ""))
        
        if not call_sid or call_sid not in secure_session_data:
            raise ValueError("Invalid or missing CallSid")
        if not address:
            raise ValueError("No address provided")

        session = secure_session_data[call_sid]
        session["address"] = address
        logging.info(f"Captured address: {address} for CallSid: {call_sid}")

        # Validate guest data using ReceptionistAgent
        guest_data = {
            "name": session["name"],
            "email": f"{session['name'].lower().replace(' ', '.')}@example.com",  # Placeholder email
            "phone": session["phone"],
            "purpose": f"Appointment with Dr. {session['doctor']} at {session['time_text']}"
        }
        validated_guest = receptionist.validate_input(guest_data)
        if not validated_guest:
            raise ValueError("Guest data validation failed")

        response = VoiceResponse()
        response.append(Play(_generate_audio_url("Confirming your booking details.")))
        response.append(Play(_generate_audio_url(
            f"You want to book with Doctor {session['doctor']} at {session['time_text']}."
        )))
        response.append(Play(_generate_audio_url(
            f"Your name is {session['name']}, phone {session['phone']}, address {session['address']}."
        )))
        response.append(Play(_generate_audio_url("Booking your appointment now.")))

        # Create appointment
        user_info = {
            "name": session["name"],
            "email": validated_guest.email
        }
        calendly_link = create_calendly_appointment(
            session["doctor"],
            "general",  # Assuming general specialty; adjust as needed
            user_info,
            session["time_text"]
        )

        if not calendly_link:
            raise ValueError("Failed to create Calendly appointment")

        # Send confirmation SMS
        send_confirmation_sms(
            session["phone"],
            session["doctor"],
            session["time_text"],
            calendly_link
        )

        response.append(Play(_generate_audio_url(
            "Your appointment has been successfully booked. A confirmation message has been sent to your phone."
        )))
        response.hangup()
        logging.info(f"Appointment booked successfully for {session['name']} with Dr. {session['doctor']}")

        # Clean up session data
        secure_session_data.pop(call_sid, None)
        return Response(str(response), mimetype='application/xml')
    except Exception as e:
        logging.error(f"Error in capture_user_address: {str(e)}")
        response = VoiceResponse()
        response.append(Play(_generate_audio_url(
            "An error occurred while booking your appointment. Please try again."
        )))
        response.redirect('/book-appointment')
        return Response(str(response), mimetype='application/xml')