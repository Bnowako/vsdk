import logging
from typing import Any, Dict

import motor.motor_asyncio
from beanie.odm.utils.init import init_beanie  # type: ignore
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.chat.router import router as chat_router
from app.config import Config
from app.plugin.router import router as plugin_router
from app.twilio.router import router as twilio_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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

    await init_beanie(database=app.database, document_models=[])

    yield
    app.mongodb_client.close()


def create_app() -> FastAPI:
    app = MongoFastAPI(lifespan=db_lifespan, openapi_prefix="/api")  # type: ignore
    app.include_router(twilio_router)
    app.include_router(plugin_router)
    app.include_router(chat_router)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    logger.info("Started application")
    return app
