import asyncio
import json
import logging
import time
from typing import Any

from fastapi import Request

from open_webui.socket.main import get_event_emitter
from open_webui.utils.chat import generate_direct_chat_completion

log = logging.getLogger(__name__)


async def vision_router_inlet(request: Request, body: dict, user: Any, metadata: dict):
    """Filter chat completion requests for vision prepass or reroute.

    Depending on configuration, either performs a lightweight JSON prepass with a
    vision model or reroutes the entire request to a vision-capable model. Metadata
    about the decision and timing is stored on the last user message.
    """

    cfg = request.app.state.config
    vr_meta = {
        "enabled": bool(getattr(cfg, "VISION_ROUTER_ENABLED", False)),
        "mode": getattr(cfg, "VISION_ROUTER_MODE", "prepass"),
        "used_model": None,
        "skipped_reason": None,
        "latency_ms": None,
        "prepass": None,
    }

    if not vr_meta["enabled"]:
        return body

    start = time.monotonic()

    try:
        messages: list[dict] = body.get("messages", [])
        if not messages:
            vr_meta["skipped_reason"] = "no_messages"
            vr_meta["latency_ms"] = int((time.monotonic() - start) * 1000)
            return body

        # Locate last user message
        last_index = next(
            (
                i
                for i in range(len(messages) - 1, -1, -1)
                if messages[i].get("role") == "user"
            ),
            None,
        )
        if last_index is None:
            vr_meta["skipped_reason"] = "no_user_message"
            vr_meta["latency_ms"] = int((time.monotonic() - start) * 1000)
            return body

        last_msg = messages[last_index]
        images = (last_msg.get("images") or [])[:4]
        content_images: list[dict] = []
        if isinstance(last_msg.get("content"), list):
            for item in last_msg["content"]:
                if item.get("type") == "image_url":
                    content_images.append(item)
        if not images and not content_images:
            vr_meta["skipped_reason"] = "no_images"
            end = time.monotonic()
            vr_meta["latency_ms"] = int((end - start) * 1000)
            last_msg.setdefault("metadata", {})["vision_router"] = vr_meta
            return body

        current_model_id = body.get("model")
        model_info = request.app.state.MODELS.get(current_model_id, {})
        if model_info.get("capabilities", {}).get("vision"):
            vr_meta["skipped_reason"] = "model_has_vision"
            end = time.monotonic()
            vr_meta["latency_ms"] = int((end - start) * 1000)
            last_msg.setdefault("metadata", {})["vision_router"] = vr_meta
            return body

        if current_model_id in getattr(cfg, "VISION_ROUTER_SKIP_MODELS", []):
            vr_meta["skipped_reason"] = "skip_list"
            end = time.monotonic()
            vr_meta["latency_ms"] = int((end - start) * 1000)
            last_msg.setdefault("metadata", {})["vision_router"] = vr_meta
            return body

        if user.role == "admin" and not getattr(
            cfg, "VISION_ROUTER_ENABLE_ADMINS", True
        ):
            vr_meta["skipped_reason"] = "admins_disabled"
            end = time.monotonic()
            vr_meta["latency_ms"] = int((end - start) * 1000)
            last_msg.setdefault("metadata", {})["vision_router"] = vr_meta
            return body
        if user.role == "user" and not getattr(cfg, "VISION_ROUTER_ENABLE_USERS", True):
            vr_meta["skipped_reason"] = "users_disabled"
            end = time.monotonic()
            vr_meta["latency_ms"] = int((end - start) * 1000)
            last_msg.setdefault("metadata", {})["vision_router"] = vr_meta
            return body

        event_emitter = None
        if getattr(cfg, "VISION_ROUTER_SHOW_STATUS_EVENTS", True):
            event_emitter = get_event_emitter(metadata)

        vision_model_id = getattr(cfg, "VISION_ROUTER_MODEL", "")

        # Reroute mode
        if vr_meta["mode"] == "reroute":
            if vision_model_id:
                body["model"] = vision_model_id
                vr_meta["used_model"] = vision_model_id
                if event_emitter:
                    await event_emitter(
                        {
                            "type": "status",
                            "data": {
                                "description": f"Request routed to {vision_model_id}",
                                "done": True,
                            },
                        }
                    )
            end = time.monotonic()
            vr_meta["latency_ms"] = int((end - start) * 1000)
            last_msg.setdefault("metadata", {})["vision_router"] = vr_meta
            return body

        # Prepass mode
        if not vision_model_id:
            vr_meta["skipped_reason"] = "no_router_model"
            end = time.monotonic()
            vr_meta["latency_ms"] = int((end - start) * 1000)
            last_msg.setdefault("metadata", {})["vision_router"] = vr_meta
            return body

        prepass_user_msg = {"role": "user"}
        if images:
            prepass_user_msg["content"] = "Describe precisely; no speculation."
            prepass_user_msg["images"] = images
        else:
            prepass_user_msg["content"] = [
                {"type": "text", "text": "Describe precisely; no speculation."},
                *content_images,
            ]

        prepass_messages = [
            {
                "role": "system",
                "content": (
                    "You are a vision model. Output a strict JSON object with keys: "
                    "caption (<=60 words), ocr_text, objects (array of {name, confidence}), "
                    "people (count), notable_details (3-8 strings), nsfw_likelihood (0-1). "
                    "No prose outside the JSON."
                ),
            },
            prepass_user_msg,
        ]

        prepass_body = {
            "model": vision_model_id,
            "messages": prepass_messages,
            "temperature": 0.2,
            "top_p": 0.9,
            "max_tokens": 400,
            "seed": 0,
            "stream": False,
        }

        prev_direct = getattr(request.state, "direct", False)
        prev_model = getattr(request.state, "model", None)
        request.state.direct = True
        request.state.model = request.app.state.MODELS.get(vision_model_id)

        try:
            res = await asyncio.wait_for(
                generate_direct_chat_completion(
                    request, prepass_body, user, request.app.state.MODELS
                ),
                timeout=15,
            )
        except Exception as e:  # Timeout or call failure
            log.exception(f"vision prepass error: {e}")
            if event_emitter:
                await event_emitter(
                    {
                        "type": "status",
                        "data": {
                            "description": "Vision prepass failed",
                            "done": True,
                        },
                    }
                )
            vr_meta["skipped_reason"] = "prepass_failed"
            end = time.monotonic()
            vr_meta["latency_ms"] = int((end - start) * 1000)
            last_msg.setdefault("metadata", {})["vision_router"] = vr_meta
            request.state.direct = prev_direct
            request.state.model = prev_model
            return body
        finally:
            request.state.direct = prev_direct
            request.state.model = prev_model

        content = (
            (res or {}).get("choices", [{}])[0].get("message", {}).get("content", "")
        )
        try:
            prepass_json = json.loads(content)
        except Exception:
            try:
                start_idx = content.find("{")
                end_idx = content.rfind("}")
                if start_idx != -1 and end_idx != -1:
                    prepass_json = json.loads(content[start_idx : end_idx + 1])
                else:
                    raise ValueError("no json object found")
            except Exception as e:
                log.exception(f"prepass json parse error: {e}")
                if event_emitter:
                    await event_emitter(
                        {
                            "type": "status",
                            "data": {
                                "description": "Vision prepass failed",
                                "done": True,
                            },
                        }
                    )
                vr_meta["skipped_reason"] = "json_parse_failed"
                end = time.monotonic()
                vr_meta["latency_ms"] = int((end - start) * 1000)
                last_msg.setdefault("metadata", {})["vision_router"] = vr_meta
                return body

        # Prepass succeeded
        vr_meta["used_model"] = vision_model_id
        end = time.monotonic()
        vr_meta["latency_ms"] = int((end - start) * 1000)
        prepass_str = json.dumps(prepass_json)
        vr_meta["prepass"] = prepass_str[:8192]
        last_msg.setdefault("metadata", {})["vision_router"] = vr_meta

        # Remove images from user message
        last_msg.pop("images", None)
        if isinstance(last_msg.get("content"), list):
            last_msg["content"] = [
                c for c in last_msg["content"] if c.get("type") != "image_url"
            ]
            if not last_msg["content"]:
                last_msg["content"] = "Describe precisely; no speculation."

        # Inject system message with JSON
        messages.insert(
            last_index,
            {
                "role": "system",
                "content": (
                    "Vision prepass (JSON below). Treat as ground truth; do not re-analyze images.\n"
                    + prepass_str
                ),
            },
        )

        if event_emitter:
            await event_emitter(
                {
                    "type": "status",
                    "data": {
                        "description": f"Vision prepass completed via {vision_model_id}",
                        "done": True,
                    },
                }
            )

        return body
    except Exception as e:
        log.exception(f"vision_router_inlet error: {e}")
        return body
