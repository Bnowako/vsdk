from typing import Any, Dict, Optional

import httpx
from pydantic import BaseModel


class NavigateRequest(BaseModel):
    url: str


class ActRequest(BaseModel):
    action: str
    variables: Optional[Dict[str, Any]] = None


class ObserveRequest(BaseModel):
    instruction: str


# Define response types
class NavigateResponse(BaseModel):
    message: str


class ActResponse(BaseModel):
    message: str


class ExtractResponse(BaseModel):
    content: str


class ObserveResponse(BaseModel):
    observations: Dict[str, Any]


class ScreenshotResponse(BaseModel):
    name: str
    screenshot: str
    message: str


class StagehandClient:
    """
    A client for interacting with the Stagehand browser automation service.
    """

    def __init__(self, base_url: str = "http://localhost:3333"):
        """
        Initialize the Stagehand client.

        Args:
            base_url: The base URL of the Stagehand service
        """
        self.client = httpx.AsyncClient(base_url=base_url)

    async def close(self) -> None:
        """Close the HTTP client connection."""
        await self.client.aclose()

    async def __aenter__(self) -> "StagehandClient":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

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
            raise StagehandError(f"Request failed: {str(e)}")

    async def navigate(self, url: str) -> NavigateResponse:
        """
        Navigate to a URL in the browser.

        This should only be used with URLs you're confident will work and stay up to date.
        Otherwise, use https://google.com as the starting point.

        Args:
            url: The URL to navigate to

        Returns:
            NavigateResponse: A message confirming navigation
        """
        response = await self._make_request("POST", "/navigate", {"url": url})
        return NavigateResponse(**response)

    async def act(
        self, action: str, variables: Optional[Dict[str, Any]] = None
    ) -> ActResponse:
        """
        Performs an action on a web page element.

        Actions should be as atomic and specific as possible, i.e. "Click the sign in button"
        or "Type 'hello' into the search input". AVOID actions that are more than one step,
        i.e. "Order me pizza" or "Send an email to Paul asking him to call me".

        Args:
            action: The specific action to perform
            variables: Variables used in the action template.
                      Only use variables for sensitive data or dynamic content.

        Returns:
            ActResponse: A message confirming the action was performed
        """
        response = await self._make_request(
            "POST", "/act", {"action": action, "variables": variables or {}}
        )
        return ActResponse(**response)

    async def extract(self) -> ExtractResponse:
        """
        Extracts all of the text from the current page.

        This endpoint filters out CSS and other non-content elements to provide clean text output.

        Returns:
            ExtractResponse: The extracted text content from the page
        """
        response = await self._make_request("GET", "/extract")
        return ExtractResponse(**response)

    async def observe(self, instruction: str) -> ObserveResponse:
        """
        Observes elements on the web page.

        Use this to observe elements that you can later use in an action.
        Use observe instead of extract when dealing with actionable (interactable) elements
        rather than text. More often than not, you'll want to use extract instead of observe
        when dealing with scraping or extracting structured text.

        Args:
            instruction: Instruction for observation (e.g., 'find the login button').
                        This instruction must be extremely specific.

        Returns:
            ObserveResponse: The observations from the page
        """
        response = await self._make_request(
            "POST", "/observe", {"instruction": instruction}
        )
        return ObserveResponse(**response)

    async def screenshot(self) -> ScreenshotResponse:
        """
        Takes a screenshot of the current page.

        Use this to learn where you are on the page when controlling the browser
        with Stagehand. Only use this tool when the other tools are not sufficient to get
        the information you need.

        Returns:
            ScreenshotResponse: Contains the screenshot data in base64 format along with metadata
        """
        response = await self._make_request("GET", "/screenshot")
        return ScreenshotResponse(**response)


class StagehandError(Exception):
    """Custom exception for Stagehand client errors."""

    pass
