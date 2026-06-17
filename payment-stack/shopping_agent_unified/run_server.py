#!/usr/bin/env python3
"""ADK A2A server for unified shopping agent (port 8090)."""

import json
import logging
import os
import sys
from pathlib import Path

import uvicorn
from google.adk.cli.fast_api import get_fast_api_app
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

_AGENT_ROOT = Path(__file__).resolve().parent
_ROLES_DIR = _AGENT_ROOT.parent
_UNIFIED_SCENARIO = _ROLES_DIR.parent
if str(_ROLES_DIR) not in sys.path:
  sys.path.insert(0, str(_ROLES_DIR))

from constants_unified import AGENT_PORT  # noqa: E402
from role_logging import log_op, setup_role_logger  # noqa: E402
from trusted_surface_gate import (  # noqa: E402
    clear_session_approval,
    register_immediate_checkout_approved_payload,
    register_mandate_approved_payload,
    reset_request_session_id,
    set_request_session_id,
)

_LOG_FILE = Path(os.environ.get("LOGS_DIR", _UNIFIED_SCENARIO / ".logs")) / (
    "shopping-agent-unified.log"
)
_logger = setup_role_logger(
    "shopping_agent_unified",
    log_file=_LOG_FILE,
    level=logging.INFO,
)


class A2ARequestLoggingMiddleware(BaseHTTPMiddleware):
  """Log incoming A2A requests to console + file."""

  async def dispatch(
      self, request: Request, call_next: RequestResponseEndpoint
  ) -> Response:
    session_token = None
    if request.method == "POST" and "/shopping_agent" in request.url.path:
      try:
        body = await request.body()
        if body:
          data = json.loads(body)
          method = data.get("method", "")
          params = data.get("params") or {}
          metadata = params.get("metadata") or {}
          session_id_full = str(metadata.get("sessionId", "") or "")
          session_id = session_id_full[:8] or "?"
          if session_id_full:
            session_token = set_request_session_id(session_id_full)
          if method == "message/stream":
            msg = params.get("message") or {}
            saw_mandate_approved = False
            for part in msg.get("parts") or []:
              if part.get("kind") == "text":
                log_op(
                    _logger,
                    "shopping-agent-http",
                    "A2A message/stream",
                    session=session_id,
                    text=(part.get("text") or "")[:120],
                )
                if session_id_full:
                  clear_session_approval(session_id_full)
              elif part.get("kind") == "data":
                payload = part.get("data") or {}
                msg_type = payload.get("type", "?")
                if msg_type == "mandate_approved" and session_id_full:
                  register_mandate_approved_payload(payload)
                  saw_mandate_approved = True
                elif msg_type == "immediate_checkout_approved" and session_id_full:
                  register_immediate_checkout_approved_payload(payload)
                  saw_mandate_approved = True
                elif session_id_full:
                  clear_session_approval(session_id_full)
                log_op(
                    _logger,
                    "shopping-agent-http",
                    f"A2A data/{msg_type}",
                    session=session_id,
                    item_id=payload.get("item_id"),
                    price_cap=payload.get("price_cap"),
                    payment_method=payload.get("ap2_config", {}).get(
                        "payment_method"
                    )
                    if isinstance(payload.get("ap2_config"), dict)
                    else payload.get("payment_method"),
                    source=payload.get("source"),
                )
            if session_id_full and not saw_mandate_approved:
              clear_session_approval(session_id_full)
          else:
            log_op(
                _logger,
                "shopping-agent-http",
                f"A2A {method}",
                session=session_id,
            )
      except (json.JSONDecodeError, KeyError, TypeError) as exc:
        log_op(
            _logger,
            "shopping-agent-http",
            "A2A request parse skip",
            error=str(exc),
        )
    elif request.method == "GET" and "/mandates/" in request.url.path:
      mandate_id = request.url.path.rsplit("/", 1)[-1]
      log_op(
          _logger,
          "shopping-agent-http",
          "GET mandate",
          mandate_id=mandate_id[:40],
      )
    try:
      return await call_next(request)
    finally:
      if session_token is not None:
        reset_request_session_id(session_token)


if __name__ == "__main__":
  logs_dir = os.environ.get("LOGS_DIR", str(_UNIFIED_SCENARIO / ".logs"))
  os.makedirs(logs_dir, exist_ok=True)
  port = int(os.environ.get("UNIFIED_AGENT_PORT", str(AGENT_PORT)))

  from shopping_agent.merchant_profile import get_merchant_profile

  profile = get_merchant_profile()
  print(
      f"Unified merchant default: {profile.key} ({profile.display_name}) "
      f"currency={profile.currency}"
  )
  print("Runtime merchant switching enabled (web UI + set_ap2_session_config.merchant).")
  print(f"MCP router: {_ROLES_DIR / 'merchant_router_unified' / 'server.py'}")
  print(f"HEG backend: {os.environ.get('HEG_FLIGHT_BACKEND_URL', 'http://127.0.0.1:9000')}")

  app = get_fast_api_app(
      agents_dir=str(_AGENT_ROOT),
      web=False,
      a2a=True,
      port=port,
      allow_origins=["*"],
  )
  app.add_middleware(A2ARequestLoggingMiddleware)

  @app.get("/a2a/shopping_agent/mandates/{mandate_id}")
  async def get_mandate(mandate_id: str):
    temp_db = Path(os.environ.get("TEMP_DB_DIR", _UNIFIED_SCENARIO / ".temp-db"))
    file_path = temp_db / f"{mandate_id}.sdjwt"
    if not file_path.exists():
      log_op(
          _logger,
          "shopping-agent-http",
          "mandate not found",
          mandate_id=mandate_id,
      )
      return Response(
          content="Mandate not found", status_code=404, media_type="text/plain"
      )
    log_op(
        _logger,
        "shopping-agent-http",
        "mandate served",
        mandate_id=mandate_id,
        bytes=file_path.stat().st_size,
    )
    return Response(
        content=file_path.read_text(encoding="ascii"), media_type="text/plain"
    )

  print(f"Unified shopping agent: http://127.0.0.1:{port}")
  uvicorn.run(app, host="127.0.0.1", port=port)
