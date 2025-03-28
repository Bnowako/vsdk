import logging
import os

from dotenv import load_dotenv

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
