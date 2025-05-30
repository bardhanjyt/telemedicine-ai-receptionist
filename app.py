from flask import Flask, request, Response
import os
import logging
from logging.handlers import RotatingFileHandler
from functools import wraps
from ratelimit import limits, RateLimitException
from werkzeug.security import check_password_hash
from werkzeug.exceptions import BadRequest, Unauthorized, InternalServerError
import json

# Initialize Flask application
app = Flask(__name__)

# Configure logging with rotation to prevent log file from growing indefinitely
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
handler = RotatingFileHandler('app.log', maxBytes=1000000, backupCount=5)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Rate limiting configuration: 100 calls per minute
CALLS = 100
PERIOD = 60

# API key hash for authentication, stored in environment variable
API_KEY_HASH = os.environ.get('API_KEY_HASH', 'your_hashed_api_key_here')

# Decorator to enforce API key authentication
def require_api_key(f):
    """
    Ensures requests include a valid API key in the 'X-API-Key' header.
    Raises Unauthorized if the key is missing or invalid.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key or not check_password_hash(API_KEY_HASH, api_key):
            logger.warning(f"Unauthorized access attempt from {request.remote_addr}")
            raise Unauthorized("Invalid or missing API key")
        return f(*args, **kwargs)
    return decorated

# Decorator to handle exceptions and return appropriate HTTP responses
def handle_exceptions(f):
    """
    Catches and logs exceptions, returning JSON error responses with appropriate status codes.
    Handles BadRequest, RateLimitException, and generic exceptions.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except BadRequest as e:
            logger.error(f"Bad request: {str(e)}")
            return {"error": str(e)}, 400
        except RateLimitException:
            logger.warning(f"Rate limit exceeded for {request.remote_addr}")
            return {"error": "Rate limit exceeded"}, 429
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}", exc_info=True)
            raise InternalServerError("Internal server error")
    return decorated

@app.route("/voice", methods=["POST"])
@require_api_key
@limits(calls=CALLS, period=PERIOD)
@handle_exceptions
def voice():
    """
    Handles incoming voice calls via Twilio.
    Expects JSON payload with call details.
    Returns TwiML response to control call flow.
    
    Example payload:
        {
            "CallSid": "CA1234567890abcdef1234567890abcdef",
            "From": "+12345678901",
            "To": "+10987654321"
        }
    """
    if not request.is_json:
        raise BadRequest("Request must be JSON")
    logger.info(f"Processing voice request from {request.remote_addr}")
    from services.twilio_handler import handle_call
    return handle_call(request)

@app.route("/process-intent", methods=["POST"])
@require_api_key
@limits(calls=CALLS, period=PERIOD)
@handle_exceptions
def process_intent():
    """
    Processes user intent from voice or text input.
    Expects JSON payload with intent data.
    Returns processed intent response.
    
    Example payload:
        {
            "intent": "book_appointment",
            "confidence": 0.95,
            "entities": {"doctor": "Dr. Smith"}
        }
    """
    if not request.is_json:
        raise BadRequest("Request must be JSON")
    logger.info(f"Processing intent request from {request.remote_addr}")
    from services.intent_handler import process_user_intent
    return process_user_intent(request)

@app.route("/process-selection", methods=["POST"])
@require_api_key
@limits(calls=CALLS, period=PERIOD)
@handle_exceptions
def process_selection():
    """
    Processes numeric selections from user input (e.g., DTMF tones).
    Expects JSON payload with selection data.
    Returns response based on selection.
    
    Example payload:
        {
            "Digits": "1",
            "CallSid": "CA1234567890abcdef1234567890abcdef"
        }
    """
    if not request.is_json:
        raise BadRequest("Request must be JSON")
    logger.info(f"Processing selection request from {request.remote_addr}")
    from services.intent_handler import process_numeric_selection
    return process_numeric_selection(request)

@app.route("/book-appointment", methods=["POST"])
@require_api_key
@limits(calls=CALLS, period=PERIOD)
@handle_exceptions
def book_appointment():
    """
    Handles appointment booking logic.
    Expects JSON payload with booking details.
    Returns confirmation or error response.
    
    Example payload:
        {
            "doctor_name": "Dr. Smith",
            "time": "2025-06-01T10:00:00Z",
            "user_name": "John Doe"
        }
    """
    if not request.is_json:
        raise BadRequest("Request must be JSON")
    logger.info(f"Processing appointment booking from {request.remote_addr}")
    from services.booking_handler import handle_booking
    return handle_booking()

@app.route("/capture-doctor-name", methods=["POST"])
@require_api_key
@limits(calls=CALLS, period=PERIOD)
@handle_exceptions
def doctor_name():
    """
    Captures doctor name from user input.
    Expects JSON payload with doctor name.
    Returns confirmation or error response.
    
    Example payload:
        {
            "doctor_name": "Dr. Smith"
        }
    """
    if not request.is_json:
        raise BadRequest("Request must be JSON")
    logger.info(f"Capturing doctor name from {request.remote_addr}")
    from services.booking_handler import capture_doctor_name
    return capture_doctor_name(request)

@app.route("/capture-appointment-time", methods=["POST"])
@require_api_key
@limits(calls=CALLS, period=PERIOD)
@handle_exceptions
def appointment_time():
    """
    Captures appointment time from user input.
    Expects JSON payload with time data.
    Returns confirmation or error response.
    
    Example payload:
        {
            "appointment_time": "2025-06-01T10:00:00Z"
        }
    """
    if not request.is_json:
        raise BadRequest("Request must be JSON")
    logger.info(f"Capturing appointment time from {request.remote_addr}")
    from services.booking_handler import capture_appointment_time
    return capture_appointment_time(request)

@app.route("/capture-user-name", methods=["POST"])
@require_api_key
@limits(calls=CALLS, period=PERIOD)
@handle_exceptions
def user_name():
    """
    Captures user name from input.
    Expects JSON payload with user name.
    Returns confirmation or error response.
    
    Example payload:
        {
            "user_name": "John Doe"
        }
    """
    if not request.is_json:
        raise BadRequest("Request must be JSON")
    logger.info(f"Capturing user name from {request.remote_addr}")
    from services.booking_handler import capture_user_name
    return capture_user_name(request)

@app.route("/capture-user-phone", methods=["POST"])
@require_api_key
@limits(calls=CALLS, period=PERIOD)
@handle_exceptions
def user_phone():
    """
    Captures user phone number from input.
    Expects JSON payload with phone number.
    Returns confirmation or error response.
    
    Example payload:
        {
            "user_phone": "+12345678901"
        }
    """
    if not request.is_json:
        raise BadRequest("Request must be JSON")
    logger.info(f"Capturing user phone from {request.remote_addr}")
    from services.booking_handler import capture_user_phone
    return capture_user_phone(request)

@app.route("/capture-user-address", methods=["POST"])
@require_api_key
@limits(calls=CALLS, period=PERIOD)
@handle_exceptions
def user_address():
    """
    Captures user address from input.
    Expects JSON payload with address data.
    Returns confirmation or error response.
    
    Example payload:
        {
            "user_address": "123 Main St, Springfield"
        }
    """
    if not request.is_json:
        raise BadRequest("Request must be JSON")
    logger.info(f"Capturing user address from {request.remote_addr}")
    from services.booking_handler import capture_user_address
    return capture_user_address(request)

# Run the application
if __name__ == "__main__":
    # Use port from environment variable or default to 5000
    port = int(os.environ.get("PORT", 5000))
    # Disable debug mode in production for security
    app.run(host="0.0.0.0", port=port, debug=False)