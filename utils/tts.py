import logging
import os
import re
import uuid
from typing import Optional
from elevenlabs import ElevenLabs  # ElevenLabs Python SDK
import boto3
from botocore.exceptions import ClientError
from receptionist_agent import ReceptionistAgent, GuestInfo

# Configure logging for error tracking and debugging
logging.basicConfig(
    filename='tts.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Securely load ElevenLabs API key from environment variable
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
if not ELEVENLABS_API_KEY:
    logging.error("ELEVENLABS_API_KEY environment variable not set")
    raise ValueError("ELEVENLABS_API_KEY environment variable not set")

# AWS S3 configuration for audio file storage
S3_BUCKET = os.getenv("S3_BUCKET", "tts-audio-bucket")
S3_REGION = os.getenv("AWS_REGION", "us-east-1")
if not S3_BUCKET:
    logging.error("S3_BUCKET environment variable not set")
    raise ValueError("S3_BUCKET environment variable not set")

# ElevenLabs voice configuration
ELEVENLABS_VOICE_ID = "3UFZ7Pkyx3hNTropzBlS"  # Abigail - Customer Support Agent
ELEVENLABS_MODEL = "eleven_multilingual_v2"

# Initialize ElevenLabs client
try:
    elevenlabs_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
    logging.info("ElevenLabs client initialized")
except Exception as e:
    logging.error(f"Failed to initialize ElevenLabs client: {str(e)}")
    raise

# Initialize AWS S3 client
try:
    s3_client = boto3.client('s3', region_name=S3_REGION)
    logging.info("AWS S3 client initialized")
except Exception as e:
    logging.error(f"Failed to initialize AWS S3 client: {str(e)}")
    raise

# Initialize receptionist agent for text validation
try:
    receptionist = ReceptionistAgent()
    logging.info("ReceptionistAgent initialized in tts")
except Exception as e:
    logging.error(f"Failed to initialize ReceptionistAgent: {str(e)}")
    raise

def _sanitize_text(text: str) -> str:
    """
    Sanitize text input to prevent injection and ensure safety
    
    Args:
        text (str): Text to sanitize
    
    Returns:
        str: Sanitized text
    """
    if not text:
        return ""
    # Remove dangerous characters and limit length
    sanitized = re.sub(r'[<>;{}]', '', text.strip())
    if len(sanitized) > 1000:  # Arbitrary limit to prevent abuse
        logging.warning("Text input exceeds 1000 characters, truncating")
        sanitized = sanitized[:1000]
    return sanitized

def _validate_text(text: str) -> bool:
    """
    Validate text using ReceptionistAgent to ensure appropriateness
    
    Args:
        text (str): Text to validate
    
    Returns:
        bool: True if valid, False otherwise
    """
    try:
        # Use placeholder guest data, focusing on purpose (text)
        guest_data = {
            "name": "***",
            "email": "***",
            "phone": "****",
            "purpose": text
        }
        validated_guest = receptionist.validate_input(guest_data)
        return bool(validated_guest)
    except Exception as e:
        logging.error(f"Error validating text: {str(e)}")
        return False

def _upload_to_s3(audio_data: bytes, filename: str) -> Optional[str]:
    """
    Upload audio file to AWS S3 and return public URL
    
    Args:
        audio_data (bytes): Audio file content
        filename (str): Name for the S3 object
    
    Returns:
        Optional[str]: Public URL of the uploaded audio, or None if upload fails
    """
    try:
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=filename,
            Body=audio_data,
            ContentType='audio/mpeg',
            ACL='public-read'  # Make file publicly accessible
        )
        url = f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{filename}"
        logging.info(f"Uploaded audio to S3: {url}")
        return url
    except ClientError as e:
        logging.error(f"Error uploading audio to S3: {str(e)}")
        return None

def generate_audio(text: str, voice_id: str = ELEVENLABS_VOICE_ID, model: str = ELEVENLABS_MODEL, language: str = 'en') -> Optional[str]:
    """
    Generate TTS audio using ElevenLabs and return a public URL
    
    Args:
        text (str): Text to convert to speech
        voice_id (str): ElevenLabs voice ID (default: Abigail)
        model (str): ElevenLabs model (default: eleven_multilingual_v2)
        language (str): Language code (default: en)
    
    Returns:
        Optional[str]: Public URL of the generated audio, or None if generation fails
    """
    try:
        # Sanitize and validate input text
        sanitized_text = _sanitize_text(text)
        if not sanitized_text:
            logging.warning("Empty or invalid text provided")
            return None

        if not _validate_text(sanitized_text):
            logging.error("Text validation failed")
            return None

        # Generate audio using ElevenLabs
        audio = elevenlabs_client.generate(
            text=sanitized_text,
            voice=voice_id,
            model=model,
            language=language
        )

        # Save audio temporarily and upload to S3
        filename = f"tts_{uuid.uuid4()}.mp3"
        audio_data = b''.join(audio)  # Convert generator to bytes
        audio_url = _upload_to_s3(audio_data, filename)
        if not audio_url:
            logging.error("Failed to upload audio to S3")
            return None

        logging.info(f"Generated audio for text: {sanitized_text[:50]}... URL: {audio_url}")
        return audio_url
    except Exception as e:
        logging.error(f"Error generating audio for text '{text[:50]}...': {str(e)}")
        return None# ElevenLabs TTS generation logic