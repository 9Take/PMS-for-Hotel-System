"""SlipOK API client for Thai bank slip verification."""

import httpx

from app.config import settings


async def verify_slip(slip_image_url: str) -> dict:
    """Send a slip image to SlipOK API for verification.

    Args:
        slip_image_url: Public URL of the slip image.

    Returns:
        dict with SlipOK response containing:
        - success (bool)
        - data.transRef, data.amount, data.sendingBank, etc.
    """
    if not settings.slipok_api_key:
        return {"success": False, "error": "SlipOK API key not configured"}

    headers = {
        "x-authorization": settings.slipok_api_key,
    }
    payload = {
        "url": slip_image_url,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{settings.slipok_api_url}/{settings.slipok_branch_id}",
            headers=headers,
            json=payload,
        )

    if response.status_code == 200:
        return response.json()
    else:
        return {
            "success": False,
            "error": f"SlipOK API error: {response.status_code}",
            "detail": response.text,
        }
