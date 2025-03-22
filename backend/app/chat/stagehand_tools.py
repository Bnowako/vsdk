from typing import Any, Dict

from langchain_core.tools import tool  # type: ignore

from app.chat import stagehand_client


@tool
async def navigate_to_url(url: str) -> str:
    """
    Navigate to a specific URL in the browser.
    Only use with URLs you're confident will work and stay up to date.
    Otherwise, use https://google.com as the starting point.

    Args:
        url: The URL to navigate to
    """
    response = await stagehand_client.stagehand_client.navigate(url)
    return response.message


@tool
async def perform_action(action: str) -> str:
    """
    Perform a specific action on a web page element.
    Actions should be atomic and specific, like "Click the sign in button" or "Type 'hello' into the search input".
    Avoid multi-step actions like "Order me pizza" or "Send an email".

    Args:
        action: The specific action to perform
    """
    response = await stagehand_client.stagehand_client.act(action)
    return response.message


@tool
async def extract_page_content() -> str:
    """
    Extract all text content from the current page.
    Filters out CSS and non-content elements for clean text output.
    """
    response = await stagehand_client.stagehand_client.extract()
    return response.content


@tool
async def observe_elements(instruction: str) -> Dict[str, Any]:
    """
    Observe specific elements on the web page.
    Use for finding actionable/interactable elements rather than text content.
    Instruction must be very specific, e.g., 'find the login button'.

    Args:
        instruction: Specific instruction for what to observe
    """
    response = await stagehand_client.stagehand_client.observe(instruction)
    return response.observations


# @tool
# async def take_screenshot() -> Dict[str, Any]:
#     """
#     Take a screenshot of the current page.
#     Use only when other tools are insufficient to get needed information.
#     Returns screenshot data in base64 format with metadata.
#     """
#     response = await stagehand_client.stagehand_client.screenshot()
#     return {
#         "name": response.name,
#         "screenshot": response.screenshot,
#         "message": response.message,
#     }
