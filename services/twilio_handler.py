import logging
import re
from typing import Optional
from flask import Response, request
from twilio.twiml.voice_response import VoiceResponse, Gather, Play
from elevenlabs import generate_audio  # Placeholder for ElevenLabs API

# Configure logging for error tracking and debugging
logging.basicConfig(
    filename='twilio_handler.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

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
    # Allow only alphanumeric characters and spaces for CallSid
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
        audio_url = generate_audio(
            text=text,
            voice_id=ELEVENLABS_VOICE_ID,
            model=ELEVENLABS_MODEL,
            language='en'  # Assuming English; adjust for multilingual support
        )
        logging.info(f"Generated audio URL for text: {text[:50]}...")
        return audio_url
    except Exception as e:
        logging.error(f"Error generating audio with ElevenLabs: {str(e)}")
        raise

def handle_call(request_obj) -> Response:
    """
    Handle incoming Twilio call and prompt for DTMF input
    
    Args:
        request_obj: Flask request object containing call details
    
    Returns:
        Response: TwiML response for Twilio to process
    """
    try:
        call_sid = _sanitize_input(request_obj.form.get("CallSid", ""))
        if not call_sid:
            logging.warning("Missing CallSid in request")
            response = VoiceResponse()
            response.append(Play(_generate_audio_url("An error occurred. Please try again later.")))
            response.redirect('/voice')
            return Response(str(response), mimetype='application/xml')

        logging.info(f"Handling incoming call with CallSid: {call_sid}")
        response = VoiceResponse()

        # Greet the user
        response.append(Play(_generate_audio_url(
            "Hello! This is Debadrita Bardhan, your AI Appointment Receptionist."
        )))
        response.pause(length=1)

        # Gather user input with keypad
        gather = Gather(
            input='dtmf',
            num_digits=1,
            action='/process-selection',
            method='POST',
            timeout=5
        )
        gather.append(Play(_generate_audio_url(
            "Please select an option. "
            "Press 1 to book an appointment. "
            "Press 2 to cancel an appointment. "
            "Press 3 to reschedule an appointment. "
            "Press 4 to check doctor availability. "
            "Press 5 to talk to a human agent."
        )))
        response.append(gather)

        # Handle no input
        response.append(Play(_generate_audio_url(
            "We didn't receive any input. Redirecting you to the main menu."
        )))
        response.redirect('/voice')

        logging.info(f"Call handled successfully for CallSid: {call_sid}")
        return Response(str(response), mimetype='application/xml')
    except Exception as e:
        logging.error(f"Error in handle_call for CallSid {call_sid}: {str(e)}")
        response = VoiceResponse()
        response.append(Play(_generate_audio_url("An error occurred. Please try again later.")))
        response.redirect('/voice')
        return Response(str(response), mimetype='application/xml')