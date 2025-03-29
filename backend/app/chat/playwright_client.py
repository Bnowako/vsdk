import logging
from typing import Any, Dict, List, Literal, Optional

import httpx
from pydantic import BaseModel

# class ImageContent(BaseModel):
#     type: Literal["image"]
#     """The type of content"""

#     data: str
#     """The base64-encoded image data"""

#     mimeType: str
#     """The MIME type of the image. Different providers may support different image types"""


class TextContent(BaseModel):
    type: Literal["text"]
    """The type of content"""

    text: str
    """The text content of the message"""


class ToolResult(BaseModel):
    content: List[TextContent]
    isError: Optional[bool] = None


logger = logging.getLogger(__name__)


class PlaywrightClient:
    def __init__(self, base_url: str = "http://localhost:3333"):
        """
        Initialize the Playwright client.

        Args:
            base_url: The base URL of the Playwright service
        """
        self.client = httpx.AsyncClient(base_url=base_url)

    async def _make_request(
        self, method: str, endpoint: str, json: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Helper function to make HTTP requests and handle errors.
        """
        try:
            response = await self.client.request(method, endpoint, json=json)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            raise PlaywrightClientError(f"Request failed: {str(e)}")

    async def browser_snapshot(self) -> ToolResult:
        """
        Capture accessibility snapshot of the current page, this is better than screenshot

        Returns:
            Aria snapshot of the current page
        """

        response = await self._make_request("POST", "/snapshot")
        logger.info(f"Browser snapshot response: {response}")
        return ToolResult(**response)

    async def click_element(self, element: str, ref: str) -> ToolResult:
        """
        Click on an element specified by its reference.

        Args:
            element: Human-readable element description
            ref: Exact target element reference from the page snapshot

        Returns:
            Result of the click operation
        """
        response = await self._make_request(
            "POST", "/click", json={"element": element, "ref": ref}
        )
        return ToolResult(**response)

    async def type_text(
        self, element: str, ref: str, text: str, submit: bool = False
    ) -> ToolResult:
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
        response = await self._make_request(
            "POST",
            "/type",
            json={"element": element, "ref": ref, "text": text, "submit": submit},
        )
        return ToolResult(**response)


class PlaywrightClientError(Exception):
    """Custom exception for Stagehand client errors."""

    pass


playwright_client = PlaywrightClient()
