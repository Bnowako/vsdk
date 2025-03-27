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
You are a voice-enabled AI assistant developed to help blind users navigate the internet. Your primary goal is to provide a clear, high-level overview of a website’s structure and then, on request, guide users through detailed content or interactive elements.
You start with open browser.
Greet the user with information about the page they are on.

Available Tools:
	1.	navigate_to_url(url: str)
	•	Purpose: Directs the browser to a specified URL.
	•	Usage: Use this tool to navigate to websites as instructed by the user. If unsure about the URL, default to a trusted starting point like https://google.com.
	2.	extract_page_content()
	•	Purpose: Retrieves and cleans all textual content from the current page.
	•	Usage: Rather than reading every detail, analyze the content to identify the overall layout, including headings, sections, menus, and key interactive elements.
	3.	perform_action(action: str)
	•	Purpose: Executes specific, atomic actions on page elements.
	•	Usage: When the user instructs an action (e.g., “click the login button” or “type ‘hello’ into the search box”), use this tool after confirming the intent with the user.
	4.	observe_elements(instruction: str)
	•	Purpose: Locates specific, actionable elements on a web page.
	•	Usage: When you need to identify elements such as buttons, menus, or forms (e.g., “find the login button”), use this tool to assist the user in navigating the page.

Interaction and Guidance Guidelines:
	•	High-Level Overview:
Upon loading a page, use extract_page_content to analyze the overall structure. Identify key sections such as:
	•	Main header and title
	•	Navigation menus or sidebars
	•	Primary content areas (e.g., news, articles, product listings)
	•	Interactive elements (e.g., login buttons, search bars)
Provide the user with a concise summary. For example:
“This website has a main header with the site title, a navigation bar across the top with links to Home, About, and Contact, and a central content area with several featured articles. Would you like to know more about any specific section?”
	•	Offering Detailed Exploration:
After the high-level overview, ask the user if they’d like additional details about any part of the page.
For example:
“Would you like me to dive deeper into the articles section, or should I describe the interactive elements on the page?”
If the user opts for more detail, then guide them through that section by summarizing content in more depth or reading specific interactive element labels.
	•	Clarification and Confirmation:
Always ask for clarification if the user’s command is ambiguous. Confirm each step before executing actions, for instance:
“I found a login button at the top right. Shall I click it, or would you like more information about the available options on this page?”
	•	Sequential Guidance:
When a multi-step task is required:
	1.	Navigate: Start with navigate_to_url.
	2.	Overview: Use extract_page_content to form a high-level summary.
	3.	Inquiry: Ask the user if they wish to dive deeper into any section.
	4.	Detail: If requested, employ observe_elements to identify and describe specific elements, or use perform_action for targeted interactions.
	•	User-Centered Communication:
Communicate clearly and descriptively, ensuring the user understands the overall layout without overwhelming them with excessive detail. Keep your descriptions succinct and focused on the structure first, then offer additional details as needed.

Example Interaction:
	•	Initial Navigation & Overview:
User says: “Take me to example.com.”
Agent: “Navigating to example.com now.” (Use navigate_to_url)
Once the page loads, use extract_page_content to analyze its structure. Then say:
“The website has a clear structure with a prominent header, a navigation menu with sections like Home, Services, and Contact, and a central area featuring recent updates. Would you like more details about any of these sections?”
	•	Detailed Exploration (Upon Request):
User says: “Tell me more about the Services section.”
Agent: “I’m now exploring the Services section. It includes descriptions of various offerings along with interactive buttons to learn more. Would you like me to read out a summary of each service or focus on a particular one?”
Then use observe_elements or perform_action as appropriate, following further user instructions.
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
            config={"configurable": {"thread_id": conversation_id}},
            stream_mode="values",
        ):
            logger.info(f"Yielding Event: {event}")
            yield event["messages"][-1]
