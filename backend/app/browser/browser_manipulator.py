import asyncio
from typing import List, Optional

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


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        await page.goto("https://bnowako.com")

        context = Context(browser, page)
        snapshot = await capture_aria_snapshot(context)
        print("\n".join(snapshot))
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
