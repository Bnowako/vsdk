import logging
import os

from dotenv import load_dotenv
from elevenlabs import ElevenLabs
from groq import AsyncGroq

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if not load_dotenv():
    raise Exception("Problem loading .env file")
else:
    logger.info("Loaded .env file")


class Secrets:
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")


class Config:
    MONGODB_URL = os.getenv("MONGODB_URL")
    MONGODB_DATABASE = os.getenv("MONGODB_DATABASE")

    class Eleven:
        client: ElevenLabs = ElevenLabs(api_key=Secrets.ELEVENLABS_API_KEY)
        model: str = "eleven_flash_v2_5"
        voice: str = "Xb7hH8MSUJpSbSDYk0k2"
        output_format: str = "pcm_8000"
        language: str = "pl"

        def with_model(self, model: str):
            self.model = model
            return self

    class Groq:
        async_client: AsyncGroq = AsyncGroq(api_key=Secrets.GROQ_API_KEY)
        transcription_model: str = "whisper-large-v3-turbo"
        transcription_language: str = "pl"

        def with_transcription_model(self, model: str):
            self.transcription_model = model
            return self

    class Audio:  # This is for audio in and out
        sample_rate: int = 8000
        channels: int = 1
        bits_per_sample: int = 16
        bytes_per_sample: int = bits_per_sample // 8

        silero_samples_size: int = 256  # 1 sample is 2 bytes, thus 256 samples is 512 bytes which is equal to ~32seconds
        silero_samples_size_bytes: int = silero_samples_size * bytes_per_sample
        silero_threshold: float = 0.73
        silero_min_silence_duration_ms: int = 350

        interruption_duration_ms: int = 600
