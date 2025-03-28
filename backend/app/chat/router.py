import json
import logging
import uuid

from fastapi import APIRouter, Request, WebSocket
from fastapi.templating import Jinja2Templates
from langchain_core.tools import tool  # type: ignore
from playwright.async_api import (
    async_playwright,
)

from app.browser.browser_manipulator import Context, capture_aria_snapshot
from app.chat.CustomBroAgent import CustomBroAgent
from app.chat.stagehand_client import stagehand_client

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

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        await page.goto("https://bnowako.com")
        context = Context(browser, page)

        @tool
        async def get_page_content():
            """
            Get the content of the current page.
            """
            return await capture_aria_snapshot(context)

        agent = CustomBroAgent(tools=[get_page_content])
        logger.info("Agent initialized")

        while True:
            data = await websocket.receive_text()
            logger.info(f"Received message: {data}")

            message = PostUserMessage(**json.loads(data))

            async for response in agent.chat_astream(message.content, conversation_id):
                logger.info(f"WS sent: {response.model_dump_json()}")
                await websocket.send_text(response.model_dump_json())


@router.get("/chat/status")
async def chat_status():
    response = await stagehand_client.extract()
    return {"status": "ok", "response": response}
