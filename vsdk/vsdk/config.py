import logging

from elevenlabs import ElevenLabs
from groq import AsyncGroq
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Config:
    class Eleven(BaseModel):
        client: ElevenLabs
        model: str
        voice: str
        output_format: str
        language: str
        api_key: str

        class Config:
            arbitrary_types_allowed = True

    class Groq(BaseModel):
        async_client: AsyncGroq
        transcription_model: str
        transcription_language: str
        audio_channels: int
        bytes_per_sample: int
        sample_rate: int

        class Config:
            arbitrary_types_allowed = True

    class Audio(BaseModel):
        sample_rate: int
        channels: int
        bits_per_sample: int
        bytes_per_sample: int

        silero_samples_size: int
        silero_samples_size_bytes: int
        silero_threshold: float
        silero_min_silence_duration_ms: int

        interruption_duration_ms: int
