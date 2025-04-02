import logging
import time
from typing import Annotated, AsyncIterator, Callable, List, Optional, TypedDict

from dotenv import load_dotenv
from langchain.chat_models.base import BaseChatModel
from langchain_core.messages import (
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from vsdk.stt.base import STTResult
from vsdk.ttt.base import BaseAgent, LLMResult

load_dotenv()

logger = logging.Logger(__name__)


class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


@tool
def what_day_and_time_is_it():
    """Tells the agent what day of the week and time is it"""
    return time.strftime("%A %H:%M:%S", time.localtime())


class CustomBroAgent(BaseAgent):
    def __init__(
        self,
        tools: List[BaseTool],
        llm: BaseChatModel = ChatOpenAI(model="gpt-4o"),
    ) -> None:
        logger.info("Initializing LLMAgent")
        in_memory_store = MemorySaver()
        llm_with_tools = llm.bind_tools(tools)
        tool_node = ToolNode(tools=tools)

        def chatbot(state: State) -> State:
            system_prompt = SystemMessage(
                content="""
You are a voice-enabled AI assistant developed to help blind users navigate the internet.
Your primary goal is to provide a clear, high-level overview of a website’s structure and then, on request, guide users through detailed content or interactive elements.

You start with a open browser.
Greet the user with information about the page they are on.

How to guide the user:
- When you get the snapshot of the page, explain high level structure of the page.
- If you are exmplaining the whole page in general, keep it short to a 2/3 sentences.
- If the user asks about the specific part go into the details more.


About the output:
- Return all answers in the format that is ready to be spoken out loud. All the text will be processed by a text to speech algorithm.

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
            config=self._get_configurable(conversation_id),
        ):
            if isinstance(msg, AIMessageChunk):
                # Record the time to first chunk
                if first_chunk_time is None:
                    first_chunk_time = time.time()

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

    async def chat_astream(
        self, user_query: str, conversation_id: str
    ) -> AsyncIterator[BaseMessage]:
        async for event in self.graph.astream(  # type: ignore
            input={"messages": [HumanMessage(content=user_query)]},
            config=self._get_configurable(conversation_id),
            stream_mode="values",
        ):
            logger.info(f"Yielding Event: {event}")
            yield event["messages"][-1]

    def _get_configurable(self, conversation_id: str) -> RunnableConfig:
        return {"configurable": {"thread_id": conversation_id}}
