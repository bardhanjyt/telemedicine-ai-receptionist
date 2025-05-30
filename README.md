
# AI-Driven Appointment Receptionist for Telemedicine

A fully autonomous voice agent engineered to handle end-to-end telemedicine appointment workflows, including scheduling, cancellation, and rescheduling. The system leverages:

* **GPT-4** for natural language understanding and dialog management
* **Twilio** for voice telephony and real-time speech input
* **Calendly** for calendar-based appointment scheduling
* **ElevenLabs** for multilingual, human-like text-to-speech synthesis
* **CrewAI** for modular agent orchestration and task management

## Directory Structure

* `agents/` – CrewAI agent definitions and coordination logic
* `services/` – Service layer for external integrations (Calendly, Twilio, PDF generation)
* `utils/` – Utility components, including ElevenLabs TTS functionality
* `static/` – Static resources such as generated documents (e.g., PDFs)
* `templates/` – Twilio Markup Language (TwiML) XML templates for telephony interaction

## Deployment (AWS)