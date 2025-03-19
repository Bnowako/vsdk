# VSDK - Voice SDK

VSDK is a comprehensive Voice SDK that enables the creation of voice-based AI agents and applications. It provides a seamless integration between speech-to-text (STT), text-to-text (TTT) with LLMs, and text-to-speech (TTS) capabilities.

## Features

- **Real-time Voice Communication**: Process audio input and generate voice responses with minimal latency
- **WebSocket Interface**: Enables real-time bidirectional communication
- **Modular Architecture**: Separate components for STT, TTT, and TTS processing
- **Multi-LLM Support**: Integration with various LLM providers (currently OpenAI, Groq)
- **High-Quality Voice Synthesis**: Integration with ElevenLabs for natural-sounding voice output
- **Conversation Management**: Tracks and manages conversation state and history

## Technology Stack

- **Backend**: FastAPI (Python 3.12+)
- **Audio Processing**: Silero VAD for voice activity detection
- **AI Models**:
  - **STT**: Groq (Speech-to-Text)
  - **LLM**: OpenAI/Groq for language understanding and response generation
  - **TTS**: ElevenLabs for high-quality voice synthesis
- **Others**: LangChain, LangGraph for agent workflows

## Getting Started

### Prerequisites

- Python 3.12+
- API keys for:
  - OpenAI/Groq (for LLM)
  - ElevenLabs (for TTS)

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/vsdk.git
   cd vsdk
   ```

2. Set up the backend:
   ```bash
   cd backend
   # Create and activate a virtual environment (optional but recommended)
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate

   # Install dependencies
   pip install -e .
   ```

3. Configure environment variables:
   ```bash
   cp .env.example .env
   # Edit .env file to add your API keys
   ```

### Running the Application

1. Start the backend server:
   ```bash
   cd backend
   uvicorn app.main:app --reload
   ```

2. The application will be available at:
   - Web interface: `http://localhost:8000`
   - API status: `http://localhost:8000/status`
   - WebSocket endpoint: `ws://localhost:8000/ws`

## Usage

### WebSocket API

Connect to the WebSocket endpoint to interact with the voice agent:

```javascript
const socket = new WebSocket('ws://localhost:8000/ws');

// Send audio data
socket.send(JSON.stringify({
  event: 'media',
  data: {
    media: base64EncodedAudioData,
    sid: 'your-session-id'
  }
}));

// Receive responses
socket.onmessage = (event) => {
  const data = JSON.parse(event.data);
  // Handle different event types
};
```

## Project Structure

```
backend/
├── app/
│   ├── voice_agent/         # Core voice agent functionality
│   │   ├── conversation/    # Conversation state management
│   │   ├── stt/             # Speech-to-Text processors
│   │   ├── ttt/             # Text-to-Text (LLM) processors
│   │   ├── tts/             # Text-to-Speech processors
│   │   └── voice_agent.py   # Main voice agent implementation
│   ├── audio/               # Audio processing utilities
│   ├── config.py            # Configuration settings
│   ├── main.py              # FastAPI application entry point
│   └── setup.py             # Application setup
├── templates/               # HTML templates
├── pyproject.toml           # Python project configuration
└── .env                     # Environment variables
```

## License

[Specify your license here]

## Contributing

[Contribution guidelines]
