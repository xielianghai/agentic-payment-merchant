#!/usr/bin/env python3
"""HTTP server for card initiate-payment (unified MPP, port 8093)."""

import asyncio
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

from path_setup import bootstrap_unified  # noqa: E402

bootstrap_unified(__file__)
from constants_unified import MPP_TRIGGER_PORT  # noqa: E402
from role_logging import log_op, log_op_result, setup_role_logger  # noqa: E402

import server as mcp_server  # noqa: E402

_logger = setup_role_logger("mpp-trigger", console=True)


class TriggerHandler(BaseHTTPRequestHandler):
  def log_message(self, format, *args):
    log_op(_logger, "mpp-trigger", "HTTP", message=args[0] if args else format)

  def do_POST(self):
    parsed = urlparse(self.path)
    if parsed.path != "/initiate-payment":
      self.send_response(404)
      self.end_headers()
      return
    try:
      content_length = int(self.headers.get("Content-Length", 0))
      body = self.rfile.read(content_length)
      data = json.loads(body) if body else {}
      payment_token = data.get("payment_token")
      checkout_jwt_hash = data.get("checkout_jwt_hash")
      open_checkout_hash = data.get("open_checkout_hash")
    except json.JSONDecodeError:
      self.send_response(400)
      self.send_header("Content-Type", "application/json")
      self.end_headers()
      self.wfile.write(json.dumps({"error": "invalid JSON"}).encode())
      return

    if not payment_token:
      self.send_response(400)
      self.send_header("Content-Type", "application/json")
      self.end_headers()
      self.wfile.write(json.dumps({"error": "payment_token required"}).encode())
      return

    log_op(
        _logger,
        "mpp-trigger",
        "POST /initiate-payment",
        token_prefix=str(payment_token)[:16] if payment_token else None,
        checkout_jwt_hash=checkout_jwt_hash[:16] if checkout_jwt_hash else None,
    )
    try:
      result = asyncio.run(
          mcp_server.initiate_or_settle_payment(
              "card",
              payment_token,
              checkout_jwt_hash or "",
              open_checkout_hash or "",
          )
      )
    except Exception as exc:
      log_op(
          _logger,
          "mpp-trigger",
          "initiate-payment exception",
          error=str(exc),
      )
      result = {"error": "processor_exception", "message": str(exc)}
    log_op_result(_logger, "mpp-trigger", "initiate-payment", result)
    self.send_response(200)
    self.send_header("Content-Type", "application/json")
    self.end_headers()
    self.wfile.write(json.dumps(result).encode())


class ReuseHTTPServer(HTTPServer):
  allow_reuse_address = True


if __name__ == "__main__":
  port = int(os.environ.get("UNIFIED_MPP_TRIGGER_PORT", str(MPP_TRIGGER_PORT)))
  server = ReuseHTTPServer(("127.0.0.1", port), TriggerHandler)
  print(f"Unified MPP trigger: http://localhost:{port}/initiate-payment")
  server.serve_forever()
