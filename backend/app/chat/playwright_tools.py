from langchain_core.tools import tool  # type: ignore

from app.chat.playwright_client import playwright_client


@tool
async def browser_snapshot() -> str:
    """
    Capture accessibility snapshot of the current page, this is better than screenshot

    Returns:
        Aria snapshot of the current page
    """
    response = await playwright_client.browser_snapshot()
    return " ".join([content.text for content in response.content])
