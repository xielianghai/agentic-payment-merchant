#!/usr/bin/env python3
"""HTTP server for receiving payment receipts (unified CP, port 8092)."""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

from path_setup import bootstrap_unified  # noqa: E402

bootstrap_unified(__file__)
from constants_unified import CP_TRIGGER_PORT  # noqa: E402
from role_logging import log_op, log_op_result, setup_role_logger  # noqa: E402

import server as mcp_server  # noqa: E402

_logger = setup_role_logger("cp-trigger", console=True)


class TriggerHandler(BaseHTTPRequestHandler):
  def log_message(self, format, *args):
    log_op(_logger, "cp-trigger", "HTTP", message=args[0] if args else format)

  def do_POST(self):
    parsed = urlparse(self.path)
    if parsed.path != "/payment-receipt":
      self.send_response(404)
      self.end_headers()
      return
    try:
      content_length = int(self.headers.get("Content-Length", 0))
      body = self.rfile.read(content_length)
      data = json.loads(body) if body else {}
      payment_receipt = data.get("payment_receipt")
    except json.JSONDecodeError:
      self.send_response(400)
      self.send_header("Content-Type", "application/json")
      self.end_headers()
      self.wfile.write(json.dumps({"error": "invalid JSON"}).encode())
      return

    if not payment_receipt:
      self.send_response(400)
      self.send_header("Content-Type", "application/json")
      self.end_headers()
      self.wfile.write(
          json.dumps({"error": "payment_receipt required"}).encode()
      )
      return

    log_op(
        _logger,
        "cp-trigger",
        "POST /payment-receipt",
        receipt_prefix=str(payment_receipt)[:24],
    )
    result = mcp_server.verify_payment_receipt(payment_receipt)
    log_op_result(_logger, "cp-trigger", "verify_payment_receipt", result)
    self.send_response(200)
    self.send_header("Content-Type", "application/json")
    self.end_headers()
    self.wfile.write(json.dumps({"status": "ok"}).encode())


class ReuseHTTPServer(HTTPServer):
  allow_reuse_address = True


if __name__ == "__main__":
  port = int(os.environ.get("UNIFIED_CP_TRIGGER_PORT", str(CP_TRIGGER_PORT)))
  server = ReuseHTTPServer(("127.0.0.1", port), TriggerHandler)
  print(f"Unified CP trigger: http://localhost:{port}/payment-receipt")
  server.serve_forever()
