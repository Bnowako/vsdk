"""
Langchain agent
"""

import logging
import time
from typing import AsyncIterator, Callable, List, Optional

from langchain.chat_models.base import BaseChatModel
from langchain_core.messages import (
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from app.voice_agent.domain import LLMResult, STTResult
from app.voice_agent.ttt.base import BaseAgent

logger = logging.getLogger(__name__)


@tool
def what_day_and_time_is_it():
    """Tells the agent what day of the week and time is it"""
    return time.strftime("%A %H:%M:%S", time.localtime())


class OpenAIAgent(BaseAgent):
    def __init__(self, llm: BaseChatModel, system_prompt: str) -> None:
        self.llm = llm
        self.system_prompt = system_prompt
        logger.info("Initializing LLMAgent")
        self.saver = MemorySaver()
        self.agent = create_react_agent(
            model=self.llm,
            checkpointer=self.saver,
            prompt=SystemMessage(content=self.system_prompt),
            tools=[what_day_and_time_is_it],
        )

    def __call__(
        self,
        stt_result: STTResult,
        conversation_id: str,
        callback: Optional[Callable[[LLMResult], None]] = None,
    ) -> AsyncIterator[str]:
        return self.astream(stt_result, conversation_id, callback)

    async def astream(
        self,
        stt_result: STTResult,
        conversation_id: str,
        callback: Optional[Callable[[LLMResult], None]] = None,
    ) -> AsyncIterator[str]:
        logger.error("Starting astream")

        start_time = time.time()
        first_chunk_time = None
        full_response = ""

        async for msg, _ in self.agent.astream(
            stream_mode="messages",
            input={"messages": [HumanMessage(content=stt_result.transcript)]},
            config={"configurable": {"thread_id": conversation_id}},
        ):
            if isinstance(msg, AIMessageChunk):
                # Record the time to first chunk
                if first_chunk_time is None:
                    first_chunk_time = time.time() - start_time

                # Accumulate the full response
                content: str = msg.content  # type: ignore
                full_response += content

                # Yield the content chunk
                yield content

        # Invoke the callback once at the end with all the data
        if callback:
            callback(
                LLMResult(
                    start_time=start_time,
                    end_time=time.time(),
                    first_chunk_time=first_chunk_time if first_chunk_time else 0,
                    response=full_response,
                )
            )

    async def ask(
        self, user_query: str, conversation_id: str, call_sid: Optional[str] = None
    ) -> str:
        response = await self.agent.ainvoke(
            input={"messages": [HumanMessage(content=user_query)]},
            config={
                "configurable": {"thread_id": conversation_id, "call_sid": call_sid}
            },
        )
        return response["messages"][-1].content

    async def adebug_ask(
        self, messages: list[BaseMessage], conversation_id: str
    ) -> List[BaseMessage]:
        response = self.agent.ainvoke(
            input={"messages": messages},
            config={"configurable": {"thread_id": conversation_id}},
        )
        return await response  # type: ignore
