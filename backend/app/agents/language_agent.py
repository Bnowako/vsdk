"""
Langchain agent
"""

import logging
from abc import ABC
from typing import Callable, Optional, List

import time
from langchain.chat_models.base import BaseChatModel
from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
    AIMessageChunk,
    BaseMessage,
)
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver


logger = logging.getLogger(__name__)


@tool
def what_day_and_time_is_it():
    """Tells the agent what day of the week and time is it"""
    return time.strftime("%A %H:%M:%S", time.localtime())


class Agent(ABC):
    async def ask(self, user_query: str, conversation_id: str) -> str:
        pass

    async def astream(
        self,
        user_query: str,
        conversation_id: str,
        callback: Optional[Callable[[dict], None]] = None,
    ):
        pass


class LLMAgent(Agent):
    def __init__(self, llm: BaseChatModel, system_prompt: str) -> None:
        self.saver = None
        self.agent = None
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

    async def astream(
        self,
        user_query: str,
        conversation_id: str,
        callback: Optional[Callable[[dict], None]] = None,
    ):
        logger.error("Starting astream")

        start_time = time.time()
        first_chunk_time = None
        full_response = ""

        async for msg, metadata in self.agent.astream(
            stream_mode="messages",
            input={"messages": [HumanMessage(content=user_query)]},
            config={"configurable": {"thread_id": conversation_id}},
        ):
            if isinstance(msg, AIMessageChunk):
                # Record the time to first chunk
                if first_chunk_time is None:
                    first_chunk_time = time.time() - start_time

                # Accumulate the full response
                content = msg.content
                full_response += content

                # Yield the content chunk
                yield content

        # Record the total time to generate the response
        total_time = time.time() - start_time

        # Invoke the callback once at the end with all the data
        if callback:
            callback(
                {
                    "full_response": full_response,
                    "first_chunk_time": first_chunk_time * 1000,
                    "total_time": total_time * 1000,
                }
            )

    async def adebug_ask(
        self, messages: list, conversation_id: str
    ) -> List[BaseMessage]:
        response = self.agent.ainvoke(
            input={"messages": messages},
            config={"configurable": {"thread_id": conversation_id}},
        )
        return await response
