import logging
from typing import Any
from fastapi import Request

log = logging.getLogger(__name__)

async def vision_router_inlet(request: Request, body: dict, user: Any):
    """Placeholder vision router inlet filter.

    Currently this simply returns the incoming body unchanged.
    The full vision routing logic is yet to be implemented.
    """
    try:
        cfg = request.app.state.config
        if not getattr(cfg, "VISION_ROUTER_ENABLED", False):
            return body
        # TODO: implement vision routing decision and processing
        return body
    except Exception as e:
        log.exception(f"vision_router_inlet error: {e}")
        return body
