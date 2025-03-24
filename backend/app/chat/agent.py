import logging
import time
from typing import Annotated, AsyncIterator, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool  # type: ignore
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

load_dotenv()

logger = logging.Logger(__name__)


class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


@tool
def what_day_and_time_is_it():
    """Tells the agent what day of the week and time is it"""
    return time.strftime("%A %H:%M:%S", time.localtime())


class LLMAgent:
    def __init__(
        self,
    ) -> None:
        logger.info("Initializing LLMAgent")
        in_memory_store = MemorySaver()
        llm = ChatOpenAI(model="gpt-4o")
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

    async def astream(
        self, user_query: str, conversation_id: str
    ) -> AsyncIterator[BaseMessage]:
        async for event in self.graph.astream(  # type: ignore
            input={"messages": [HumanMessage(content=user_query)]},
            config={"configurable": {"thread_id": conversation_id}},
            stream_mode="values",
        ):
            logger.info(f"Yielding Event: {event}")
            yield event["messages"][-1]
