#!/usr/bin/env python3
"""Create a persistent browser login profile."""

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).parent.parent.parent
PROFILES_DIR = ROOT / "profiles"


async def main():
    if len(sys.argv) < 2:
        print("Usage: python -m src.browser.create_profile <name>", file=sys.stderr)
        print("Example: python -m src.browser.create_profile amazon", file=sys.stderr)
        sys.exit(1)

    name = sys.argv[1]
    profile_path = PROFILES_DIR / name
    profile_path.mkdir(parents=True, exist_ok=True)

    print(f'Opening browser with profile "{name}" at {profile_path}')
    print("Log in to the site, then close the browser window to save the profile.\n")

    pw = await async_playwright().start()
    context = await pw.chromium.launch_persistent_context(
        str(profile_path),
        headless=False,
        viewport={"width": 1280, "height": 720},
        args=["--disable-gpu"],
    )

    page = context.pages[0] if context.pages else await context.new_page()
    await page.goto("about:blank")

    # Wait for the user to close the browser
    closed = asyncio.get_event_loop().create_future()
    context.on("close", lambda: closed.set_result(True))
    await closed

    await pw.stop()
    print(f'\nProfile "{name}" saved to {profile_path}')


if __name__ == "__main__":
    asyncio.run(main())
