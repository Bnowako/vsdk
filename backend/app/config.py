import os
from typing import Dict, Any
from beanie.odm.utils.init import init_beanie  # type: ignore
from fastapi import FastAPI
import motor.motor_asyncio
from fastapi.middleware.cors import CORSMiddleware
import logging
from dotenv import load_dotenv
from .example.router import router as example_router
from .example.models import ExampleDocument
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
        model: str = "eleven_turbo_v2_5"
        voice: str = "Xb7hH8MSUJpSbSDYk0k2"
        output_format: str = "ulaw_8000"

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


class MongoFastAPI(FastAPI):
    mongodb_client: motor.motor_asyncio.AsyncIOMotorClient[Dict[str, Any]]
    database: motor.motor_asyncio.AsyncIOMotorDatabase[Dict[str, Any]]


async def db_lifespan(app: MongoFastAPI):
    # Startup
    app.mongodb_client = motor.motor_asyncio.AsyncIOMotorClient(Config.MONGODB_URL)
    app.database = app.mongodb_client.get_database(Config.MONGODB_DATABASE)
    ping_response = await app.database.command("ping")

    if int(ping_response["ok"]) != 1:
        raise Exception(
            "Problem connecting to database cluster. For local development run docker run -d -p 27017:27017 mongo"
        )
    else:
        logger.info("Connected to database cluster.")

    await init_beanie(
        database=app.database,
        document_models=[
            ExampleDocument,
        ],
    )

    yield
    app.mongodb_client.close()


def create_app() -> FastAPI:
    app = MongoFastAPI(lifespan=db_lifespan, openapi_prefix="/api")  # type: ignore
    app.include_router(example_router)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    logger.info("Started application")
    return app
