import logging
import time
from typing import Annotated, AsyncIterator, Callable, Optional, TypedDict

from dotenv import load_dotenv
from langchain.chat_models.base import BaseChatModel
from langchain_core.messages import (
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.chat.stagehand_tools import (
    extract_page_content,
    navigate_to_url,
    observe_elements,
    perform_action,
)
from app.voice_agent.domain import LLMResult, STTResult
from app.voice_agent.ttt.base import BaseAgent

load_dotenv()

logger = logging.Logger(__name__)


class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


@tool
def what_day_and_time_is_it():
    """Tells the agent what day of the week and time is it"""
    return time.strftime("%A %H:%M:%S", time.localtime())


class BroAgent(BaseAgent):
    def __init__(
        self,
        llm: BaseChatModel = ChatOpenAI(model="gpt-4o"),
    ) -> None:
        logger.info("Initializing LLMAgent")
        in_memory_store = MemorySaver()
        llm_with_tools = llm.bind_tools(  # type: ignore
            [
                what_day_and_time_is_it,
                navigate_to_url,
                extract_page_content,
                perform_action,
                observe_elements,
            ]
        )

        tool_node = ToolNode(
            tools=[
                what_day_and_time_is_it,
                navigate_to_url,
                perform_action,
                extract_page_content,
                observe_elements,
            ]
        )

        def chatbot(state: State) -> State:
            system_prompt = SystemMessage(
                content="""
You are a helpful assistant that is able to browse the internet.

Answer in Concise manner. Start always with a general high level overwiew and only if user asks for more details, use the tools to provide more details.
All the things you say will be spoken out loud, so don't use any special characters, markdown or other formatting.
Additinally you should output short responses that can be easily spoken out loud.
You always have a browser to your disposal.

You can use the following tools to help the user:
- navigate_to_url
- extract_page_content
- perform_action
- observe_elements

You can also use the following tools to help the user:
- what_day_and_time_is_it

You can use the following tools to help the user:
- navigate_to_url
- extract_page_content

Speak only in Polish.
"""
            )
            msgs = [system_prompt] + state["messages"]
            return {"messages": [llm_with_tools.invoke(msgs)]}

        graph_builder = StateGraph(State)
        graph_builder.add_node("chatbot", chatbot)  # type: ignore
        graph_builder.add_node("tools", tool_node)  # type: ignore

        graph_builder.add_conditional_edges(
            "chatbot",
            tools_condition,
        )
        graph_builder.add_edge(START, "chatbot")
        graph_builder.add_edge("tools", "chatbot")
        graph_builder.add_edge("chatbot", END)

        self.graph: CompiledStateGraph = graph_builder.compile(
            checkpointer=in_memory_store,
        )  # type: ignore

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

        async for msg, _ in self.graph.astream(
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
