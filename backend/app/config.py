import logging
import os

from dotenv import load_dotenv
from elevenlabs import ElevenLabs
from groq import AsyncGroq

from vsdk.config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if not load_dotenv():
    raise Exception("Problem loading .env file")
else:
    logger.info("Loaded .env file")


if not (ELEVENLABS_API_KEY := os.getenv("ELEVENLABS_API_KEY")):
    raise ValueError("ELEVENLABS_API_KEY environment variable is required")

if not (GROQ_API_KEY := os.getenv("GROQ_API_KEY")):
    raise ValueError("GROQ_API_KEY environment variable is required")

ELEVEN_CONFIG = Config.Eleven(
    client=ElevenLabs(api_key=ELEVENLABS_API_KEY),
    model="eleven_flash_v2_5",
    voice="Xb7hH8MSUJpSbSDYk0k2",
    output_format="pcm_16000",
    language="en",
    api_key=ELEVENLABS_API_KEY,
)

GROQ_CONFIG = Config.Groq(
    async_client=AsyncGroq(api_key=GROQ_API_KEY),
    transcription_model="whisper-large-v3-turbo",
    transcription_language="en",
    audio_channels=1,
    bytes_per_sample=16 // 8,
    sample_rate=8000,
)

AUDIO_CONFIG = Config.Audio(
    sample_rate=8000,
    channels=1,
    bits_per_sample=16,
    bytes_per_sample=16 // 8,
    silero_samples_size=256,
    silero_samples_size_bytes=256 * 2,
    silero_threshold=0.73,
    silero_min_silence_duration_ms=350,
    interruption_duration_ms=600,
)
