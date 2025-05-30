import logging
from typing import Optional
from flask import Response, request
from twilio.twiml.voice_response import VoiceResponse, Play
from elevenlabs import generate_audio  # Placeholder for ElevenLabs API

# Configure logging for error tracking and debugging
logging.basicConfig(
    filename='intent_handler.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# ElevenLabs voice configuration
ELEVENLABS_VOICE_ID = "3UFZ7Pkyx3hNTropzBlS"  # Abigail - Customer Support Agent
ELEVENLABS_MODEL = "eleven_multilingual_v2"

# Secure configuration for human support number
HUMAN_SUPPORT_NUMBER = os.getenv("HUMAN_SUPPORT_NUMBER", "****")  # Fallback number
if not HUMAN_SUPPORT_NUMBER.startswith("+"):
    logging.error("Invalid HUMAN_SUPPORT_NUMBER format")
    raise ValueError("HUMAN_SUPPORT_NUMBER must start with '+'")

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
    # Allow only digits for DTMF input
    return re.sub(r'[^0-9]', '', input_str.strip())

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
            language='en'  
        )
        logging.info(f"Generated audio URL for text: {text[:50]}...")
        return audio_url
    except Exception as e:
        logging.error(f"Error generating audio with ElevenLabs: {str(e)}")
        raise

def process_numeric_selection(request_obj) -> Response:
    """
    Process numeric DTMF input and redirect to appropriate endpoint
    
    Args:
        request_obj: Flask request object containing DTMF digits
    
    Returns:
        Response: TwiML response for Twilio to process
    """
    try:
        digit = _sanitize_input(request_obj.form.get("Digits", ""))
        call_sid = _sanitize_input(request_obj.form.get("CallSid", ""))
        if not call_sid:
            logging.error("Missing CallSid in request")
            raise ValueError("Missing CallSid")
        if not digit:
            logging.warning(f"No digit provided for CallSid: {call_sid}")
            response = VoiceResponse()
            response.append(Play(_generate_audio_url("Invalid input. Let's try again.")))
            response.redirect('/voice')
            return Response(str(response), mimetype='application/xml')

        response = VoiceResponse()
        logging.info(f"Processing digit {digit} for CallSid: {call_sid}")

        if digit == '1':
            response.append(Play(_generate_audio_url("Great! Let's book your appointment.")))
            response.redirect('/book-appointment')
        elif digit == '2':
            response.append(Play(_generate_audio_url("Okay, let's cancel your appointment.")))
            response.redirect('/cancel-appointment')
        elif digit == '3':
            response.append(Play(_generate_audio_url("Sure, we will reschedule your appointment.")))
            response.redirect('/reschedule-appointment')
        elif digit == '4':
            response.append(Play(_generate_audio_url("Checking doctor availability now.")))
            response.redirect('/check-availability')
        elif digit == '5':
            response.append(Play(_generate_audio_url("Connecting you to a human agent now.")))
            response.dial(HUMAN_SUPPORT_NUMBER)
        else:
            response.append(Play(_generate_audio_url("Invalid input. Let's try again.")))
            response.redirect('/voice')

        return Response(str(response), mimetype='application/xml')
    except Exception as e:
        logging.error(f"Error in process_numeric_selection: {str(e)}")
        response = VoiceResponse()
        response.append(Play(_generate_audio_url("An error occurred. Please try again later.")))
        response.redirect('/voice')
        return Response(str(response), mimetype='application/xml')