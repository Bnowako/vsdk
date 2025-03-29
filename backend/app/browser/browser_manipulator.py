import asyncio
from typing import List, Optional, Union

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool  # type: ignore
from playwright.async_api import (
    Browser,
    ElementHandle,
    Frame,
    Locator,
    Page,
    async_playwright,
)


class Context:
    def __init__(self, browser: Browser, page: Page):
        self.browser = browser
        self.page = page
        self.last_snapshot: List[str] = []
        self._last_snapshot_frames: List[Frame] = []

    def existing_page(self) -> Page:
        return self.page

    def ref_locator(self, ref: str) -> Locator:
        import re

        page = self.existing_page()
        frame: Union[Frame, Locator] = page.main_frame

        match = re.match(r"^f(\d+)(.*)", ref)
        if match:
            frame_index = int(match.group(1))
            if not self._last_snapshot_frames[frame_index]:
                raise ValueError(
                    "Frame does not exist. Provide ref from the most current snapshot."
                )
            frame = self._last_snapshot_frames[frame_index]
            ref = match.group(2)

        return frame.locator(f"aria-ref={ref}")

    # todo debug this function and make sure I know how it
    async def all_frames_snapshot(self) -> str:
        page = self.existing_page()
        visible_frames: List[Locator] = (
            await page.locator("iframe").filter(visible=True).all()
        )

        # Get content frames for each iframe
        self._last_snapshot_frames = [
            await frame.content_frame() for frame in visible_frames
        ]

        # Get main page snapshot
        main_snapshot: str = await page.locator("html").aria_snapshot()

        # Get snapshots for each iframe
        frame_snapshots: List[str] = []
        for index, frame in enumerate(self._last_snapshot_frames):
            snapshot: str = await frame.locator("html").aria_snapshot()
            args: List[str] = []

            # Get iframe attributes
            owner: ElementHandle = frame.owner()
            src: Optional[str] = await owner.get_attribute("src")
            if src:
                args.append(f"src={src}")

            name: Optional[str] = await owner.get_attribute("name")
            if name:
                args.append(f"name={name}")

            # Replace ref attributes in snapshot
            modified_snapshot: str = snapshot.replace("[ref=", f"[ref=f{index}")
            frame_snapshots.append(f"\n# iframe {' '.join(args)}\n{modified_snapshot}")

        # Combine all snapshots
        return "\n".join([main_snapshot] + frame_snapshots)


async def capture_aria_snapshot(context: Context) -> List[str]:
    page = context.existing_page()
    lines: List[str] = []

    lines.append(f"Page: {page.url}")
    lines.append(f"Title: {page.title()}")

    snapshot: str = await context.all_frames_snapshot()
    lines.append(snapshot)
    return lines


@tool
async def browser_snapshot(config: RunnableConfig) -> List[str]:
    """
    Capture the current page content.
    """
    context = config.get("configurable", {}).get("context", None)
    if not context:
        raise ValueError("Context not found in config")

    return await capture_aria_snapshot(context)


@tool
async def browser_click(ref: str, config: RunnableConfig) -> None:
    """
    Perform click on a web page.

    Args:
        ref: Exact target element reference from the page snapshot.
    """
    # https://playwright.dev/python/docs/locators#locate-by-css-or-xpath
    context = config.get("configurable", {}).get("context", None)
    if not context:
        raise ValueError("Context not found in config")

    await context.ref_locator(ref).click()


bro_tools = [browser_snapshot, browser_click]


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        await page.goto("https://bnowako.com")

        context = Context(browser, page)
        snapshot = await capture_aria_snapshot(context)
        print("\n".join(snapshot))

        await context.ref_locator('link "about"').click()

        snapshot = await capture_aria_snapshot(context)
        print("\n".join(snapshot))

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
