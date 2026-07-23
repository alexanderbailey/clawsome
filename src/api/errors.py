from fastapi.responses import JSONResponse
from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError


def classify_playwright_error(exc: Exception) -> str:
    """Bucket a Playwright failure into a coarse, client-friendly category.

    Selector-not-found surfaces as a TimeoutError (Playwright waits for the
    selector until the timeout), so its detail rides along in the message.
    """
    if isinstance(exc, PlaywrightTimeoutError):
        return "timeout"
    msg = str(exc).lower()
    if "net::" in msg or "err_" in msg or "navigat" in msg or "frame was detached" in msg:
        return "navigation"
    return "error"


def playwright_error_response(
    exc: Exception, *, url: str | None = None, status_code: int = 400
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": classify_playwright_error(exc),
            "message": str(exc).strip() or exc.__class__.__name__,
            "url": url,
        },
    )
