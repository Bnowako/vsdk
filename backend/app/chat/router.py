import json
import logging
import uuid

from fastapi import APIRouter, Request, WebSocket
from fastapi.templating import Jinja2Templates

from app.chat.stagehand_client import stagehand_client

from .agent import LLMAgent
from .schemas import PostUserMessage

router = APIRouter()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

templates = Jinja2Templates(directory="templates")


@router.get("/chat")
async def chat_page(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request})


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
async def chat_status():
    response = await stagehand_client.extract()
    return {"status": "ok", "response": response}
