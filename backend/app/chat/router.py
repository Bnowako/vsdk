import json
import logging
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, WebSocket

from app.chat.stagehand_client import StagehandClient

from .agent import LLMAgent
from .schemas import PostUserMessage

router = APIRouter()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


async def get_stagehand_client() -> AsyncGenerator[StagehandClient, None]:
    """Dependency that provides a StagehandClient instance"""
    client = StagehandClient(base_url="http://localhost:3333")
    try:
        yield client
    finally:
        await client.close()


# create web socket connection for chat
@router.websocket("/chat")
async def chat(websocket: WebSocket):
    await websocket.accept()
    conversation_id = str(uuid.uuid4())
    logger.info("WebSocket connection accepted")

    agent = LLMAgent()
    logger.info("Agent initialized")
    while True:
        data = await websocket.receive_text()
        logger.info(f"Received message: {data}")

        message = PostUserMessage(**json.loads(data))

        async for response in agent.astream(message.content, conversation_id):
            logger.info(f"WS sent: {response.model_dump_json()}")
            await websocket.send_text(response.model_dump_json())


@router.get("/chat/status")
async def chat_status(
    stagehand_client: StagehandClient = Depends(get_stagehand_client),
):
    response = await stagehand_client.extract()
    return {"status": "ok", "response": response}
