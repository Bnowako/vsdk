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


@tool
async def click_element(element: str, ref: str) -> str:
    """
    Click on an element specified by its reference.

    Args:
        element: Human-readable element description
        ref: Exact target element reference from the page snapshot

    Returns:
        Result of the click operation
    """
    response = await playwright_client.click_element(element, ref)
    return " ".join([content.text for content in response.content])


@tool
async def type_text(element: str, ref: str, text: str, submit: bool = False) -> str:
    """
    Type text into an element specified by its reference.

    Args:
        element: Human-readable element description
        ref: Exact target element reference from the page snapshot
        text: Text to type into the element
        submit: Whether to submit entered text (press Enter after)

    Returns:
        Result of the type operation
    """
    response = await playwright_client.type_text(element, ref, text, submit)
    return " ".join([content.text for content in response.content])
