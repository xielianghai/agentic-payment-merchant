#!/usr/bin/env python3
"""HTTP server for x402 settle-payment (unified, port 8094)."""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

from path_setup import bootstrap_unified  # noqa: E402

bootstrap_unified(__file__)
from constants_unified import X402_PSP_TRIGGER_PORT  # noqa: E402
from role_logging import log_op, log_op_result, setup_role_logger  # noqa: E402

from roles.x402_psp_mcp import server as x402_psp  # noqa: E402

_logger = setup_role_logger("x402-trigger", console=True)


class TriggerHandler(BaseHTTPRequestHandler):
  def log_message(self, format, *args):
    log_op(_logger, "x402-trigger", "HTTP", message=args[0] if args else format)

  def do_POST(self):
    parsed = urlparse(self.path)
    if parsed.path != "/settle-payment":
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
        "x402-trigger",
        "POST /settle-payment",
        token_prefix=str(payment_token)[:16] if payment_token else None,
    )
    try:
      result = x402_psp.settle_payment(
          payment_token,
          checkout_jwt_hash,
          open_checkout_hash,
      )
    except Exception as exc:
      log_op(
          _logger,
          "x402-trigger",
          "settle-payment exception",
          error=str(exc),
      )
      result = {
          "error": "settlement_exception",
          "message": str(exc),
      }
    log_op_result(_logger, "x402-trigger", "settle-payment", result)
    self.send_response(200)
    self.send_header("Content-Type", "application/json")
    self.end_headers()
    self.wfile.write(json.dumps(result).encode())


class ReuseHTTPServer(HTTPServer):
  allow_reuse_address = True


if __name__ == "__main__":
  port = int(os.environ.get("UNIFIED_X402_PSP_TRIGGER_PORT", str(X402_PSP_TRIGGER_PORT)))
  server = ReuseHTTPServer(("127.0.0.1", port), TriggerHandler)
  print(f"Unified x402 PSP trigger: http://localhost:{port}/settle-payment")
  server.serve_forever()
