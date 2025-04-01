import json
import logging
import uuid

from fastapi import APIRouter, Request, WebSocket
from fastapi.templating import Jinja2Templates
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp import ClientSession, StdioServerParameters, stdio_client  # type: ignore

from app.chat.CustomBroAgent import CustomBroAgent
from app.chat.stagehand_client import stagehand_client

from .schemas import PostUserMessage

router = APIRouter()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

templates = Jinja2Templates(directory="templates")


# Create server parameters for stdio connection
server_params = StdioServerParameters(
    command="npx",  # Executable
    args=["@playwright/mcp@latest"],  # Optional command line arguments
    env=None,  # Optional environment variables
)


@router.get("/chat")
async def chat_page(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request})


# create web socket connection for chat
@router.websocket("/chat")
async def chat(websocket: WebSocket):
    await websocket.accept()
    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            lang_tools = await load_mcp_tools(session)
            logger.info(f"Lang tools: {lang_tools}")

            conversation_id = str(uuid.uuid4())
            logger.info("WebSocket connection accepted")

            agent = CustomBroAgent(tools=lang_tools)
            logger.info("Agent initialized")

            while True:
                data = await websocket.receive_text()
                logger.info(f"Received message: {data}")

                message = PostUserMessage(**json.loads(data))

                async for response in agent.chat_astream(
                    message.content, conversation_id
                ):
                    logger.info(f"WS sent: {response.model_dump_json()}")
                    await websocket.send_text(response.model_dump_json())


@router.get("/chat/status")
async def chat_status():
    response = await stagehand_client.extract()
    return {"status": "ok", "response": response}
