import os
import secrets

from fastapi import Header, HTTPException

# When set, every /api/* route requires `Authorization: Bearer <token>`.
# When unset, the API is unauthenticated and behaviour is unchanged.
CLAWSOME_TOKEN = os.environ.get("CLAWSOME_TOKEN") or None


async def require_token(authorization: str | None = Header(default=None)):
    if not CLAWSOME_TOKEN:
        return
    scheme, _, credentials = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(
        credentials.encode(), CLAWSOME_TOKEN.encode()
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
