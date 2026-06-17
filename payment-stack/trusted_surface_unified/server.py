#!/usr/bin/env python3
"""H5 Trusted Surface HTTP server (standalone AP2 role, port 8104).

Endpoints:
  POST /ts/sessions          - freeze mandate draft, return portal_url
  GET  /ts/confirm           - H5 confirmation page
  GET  /ts/mandate           - authoritative frozen draft JSON
  GET  /ts/passkey/options   - WebAuthn register/auth options (mandate-bound)
  POST /ts/passkey/register  - verify passkey registration + approve
  POST /ts/passkey/verify    - verify passkey assertion + approve
  POST /ts/approve           - user confirms (+ optional PIN fallback)
  GET  /ts/status            - pending | signed | expired
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

_ROLES_DIR = Path(__file__).resolve().parents[1]
_AGENT_DIR = _ROLES_DIR / "shopping_agent_unified"
if str(_ROLES_DIR) not in sys.path:
  sys.path.insert(0, str(_ROLES_DIR))
if str(_AGENT_DIR) not in sys.path:
  sys.path.insert(0, str(_AGENT_DIR))

from path_setup import bootstrap_unified  # noqa: E402

bootstrap_unified(__file__)
import passkey  # noqa: E402
from role_logging import log_op, setup_role_logger  # noqa: E402
from trusted_surface_gate import (  # noqa: E402
  confirm_trusted_surface_approval,
  create_ts_session,
  get_trusted_surface_draft,
  get_ts_session_status,
)

_logger = setup_role_logger("trusted-surface", console=True)

PORT = int(
    os.environ.get(
        "UNIFIED_TRUSTED_SURFACE_PORT",
        os.environ.get("TRUSTED_SURFACE_PORT", "8104"),
    )
)

CONFIRM_PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AP2 Trusted Surface</title>
  <style>
    :root { font-family: system-ui, sans-serif; color: #111; background: #f6f7fb; }
    body { margin: 0; padding: 24px; display: flex; justify-content: center; }
    .card {
      background: #fff; border-radius: 12px; box-shadow: 0 8px 24px rgba(0,0,0,.08);
      max-width: 480px; width: 100%; padding: 24px;
    }
    .card-header {
      display: flex; align-items: flex-start; justify-content: space-between;
      gap: 12px; margin-bottom: 8px;
    }
    .card-header h1 { font-size: 1.25rem; margin: 0; flex: 1; }
    h1 { font-size: 1.25rem; margin: 0 0 8px; }
    .subtitle { color: #555; margin-bottom: 20px; font-size: .95rem; }
    dl { margin: 0 0 20px; }
    dt { font-size: .75rem; text-transform: uppercase; color: #666; margin-top: 12px; }
    dd { margin: 4px 0 0; font-size: 1rem; font-weight: 600; }
    label { display: block; font-size: .85rem; margin-bottom: 6px; color: #444; }
    input[type=password] {
      width: 100%; box-sizing: border-box; padding: 10px 12px; border: 1px solid #ccc;
      border-radius: 8px; font-size: 1rem;
    }
    button {
      width: 100%; margin-top: 16px; padding: 12px; border: 0; border-radius: 8px;
      background: #0b57d0; color: #fff; font-size: 1rem; font-weight: 600; cursor: pointer;
    }
    button.secondary {
      background: #fff; color: #0b57d0; border: 1px solid #c7d7f5;
    }
    button.close-btn {
      width: auto; margin: 0; flex-shrink: 0; padding: 6px 12px;
      background: #fff; color: #555; border: 1px solid #dde3ee;
      font-size: .85rem; font-weight: 600; line-height: 1.2;
    }
    button.close-btn:hover { background: #f6f7fb; color: #111; }
    button.close-primary {
      background: #fff; color: #137333; border: 1px solid #b7dfc0;
    }
    button.close-primary:hover { background: #f3faf5; }
    button:disabled { opacity: .5; cursor: not-allowed; }
    .error { color: #b3261e; margin-top: 12px; }
    .success { color: #137333; margin-top: 12px; font-weight: 600; }
    .hint { color: #666; font-size: .85rem; margin-top: 8px; }
    .auth-section {
      border: 1px solid #dde3ee; border-radius: 10px; padding: 14px; margin-top: 12px;
      background: #fbfcff;
    }
    .auth-title { font-weight: 700; margin-bottom: 8px; }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 999px;
      background: #e8f0fe; color: #0b57d0; font-size: .75rem; font-weight: 600; }
    #pinFallback { margin-top: 12px; }
    #pinBlock[hidden] { display: none; }
  </style>
</head>
<body>
  <div class="card">
    <div class="card-header">
      <h1>Confirm purchase</h1>
      <button id="closeBtn" type="button" class="close-btn" aria-label="Close">Close</button>
    </div>
    <p class="subtitle">Review the frozen mandate below, then authorize.</p>
    <div id="loading">Loading mandate...</div>
    <div id="content" hidden>
      <dl>
        <dt>Product</dt><dd id="product">-</dd>
        <dt>Price cap</dt><dd id="price">-</dd>
        <dt>Payment</dt><dd id="payment">-</dd>
        <dt>Mode</dt><dd id="mode">-</dd>
        <dt>Reference</dt><dd id="ref" style="font-weight:400;font-size:.85rem;word-break:break-all;">-</dd>
      </dl>
      <div id="pinFallback" class="auth-section">
        <div id="pinBlock">
          <div class="auth-title">Confirm with PIN</div>
          <label for="pin">Security PIN</label>
          <input type="password" id="pin" inputmode="numeric" autocomplete="off" placeholder="Enter PIN" />
          <p id="pinHint" class="hint" hidden></p>
          <button id="pinConfirmBtn" type="button">Confirm with PIN</button>
        </div>
      </div>
      <div class="auth-section">
        <div class="auth-title">Confirm with Touch ID</div>
        <button id="passkeyBtn" type="button" class="secondary">Use Touch ID</button>
        <p class="hint">If Chrome shows a passkey storage picker, cancel it and use PIN instead.</p>
      </div>
      <div id="message"></div>
      <button id="closeAfterSignBtn" type="button" class="close-primary" hidden>Close window</button>
    </div>
  </div>
  <script>
    const params = new URLSearchParams(location.search);
    const ref = params.get('ref') || '';
    const loading = document.getElementById('loading');
    const content = document.getElementById('content');
    const message = document.getElementById('message');
    const passkeyBtn = document.getElementById('passkeyBtn');
    const pinConfirmBtn = document.getElementById('pinConfirmBtn');
    const pinInput = document.getElementById('pin');
    const pinBlock = document.getElementById('pinBlock');
    const pinFallback = document.getElementById('pinFallback');
    const pinHint = document.getElementById('pinHint');
    const closeBtn = document.getElementById('closeBtn');
    const closeAfterSignBtn = document.getElementById('closeAfterSignBtn');
    let pinRequired = false;

    const TS_CLOSE_STORAGE_KEY = 'ap2_ts_close_all';
    const TS_CLOSE_CHANNEL = 'ap2-ts-close';

    function closeCurrentWindow() {
      try { window.close(); } catch (_) {}
    }

    function closeAllTrustedSurfacePages() {
      const stamp = String(Date.now());
      try { localStorage.setItem(TS_CLOSE_STORAGE_KEY, stamp); } catch (_) {}
      try {
        const bc = new BroadcastChannel(TS_CLOSE_CHANNEL);
        bc.postMessage({ action: 'close', at: stamp });
        bc.close();
      } catch (_) {}
      closeCurrentWindow();
      setTimeout(() => {
        if (!document.hidden) {
          message.className = 'hint';
          message.textContent = 'If this tab stays open, close it manually.';
        }
      }, 400);
    }

    window.addEventListener('storage', (e) => {
      if (e.key === TS_CLOSE_STORAGE_KEY && e.newValue) closeCurrentWindow();
    });
    try {
      const closeChannel = new BroadcastChannel(TS_CLOSE_CHANNEL);
      closeChannel.onmessage = () => closeCurrentWindow();
    } catch (_) {}

    closeBtn.addEventListener('click', closeAllTrustedSurfacePages);
    closeAfterSignBtn.addEventListener('click', closeAllTrustedSurfacePages);

    function bufferToBase64url(buffer) {
      const bytes = new Uint8Array(buffer);
      let str = '';
      for (const b of bytes) str += String.fromCharCode(b);
      return btoa(str).replace(/\\+/g, '-').replace(/\\//g, '_').replace(/=+$/, '');
    }

    function base64urlToBuffer(base64url) {
      const pad = '='.repeat((4 - base64url.length % 4) % 4);
      const b64 = (base64url + pad).replace(/-/g, '+').replace(/_/g, '/');
      const binary = atob(b64);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      return bytes.buffer;
    }

    function decodeCreationOptions(publicKey) {
      const opts = structuredClone(publicKey);
      opts.challenge = base64urlToBuffer(opts.challenge);
      if (opts.user && opts.user.id) opts.user.id = base64urlToBuffer(opts.user.id);
      if (Array.isArray(opts.excludeCredentials)) {
        opts.excludeCredentials = opts.excludeCredentials.map((cred) => ({
          ...cred,
          id: base64urlToBuffer(cred.id),
        }));
      }
      return opts;
    }

    function decodeRequestOptions(publicKey) {
      const opts = structuredClone(publicKey);
      opts.challenge = base64urlToBuffer(opts.challenge);
      if (Array.isArray(opts.allowCredentials)) {
        opts.allowCredentials = opts.allowCredentials.map((cred) => ({
          ...cred,
          id: base64urlToBuffer(cred.id),
        }));
      }
      return opts;
    }

    function credentialToJson(credential) {
      const response = credential.response;
      const out = {
        id: credential.id,
        rawId: bufferToBase64url(credential.rawId),
        type: credential.type,
        clientExtensionResults: credential.getClientExtensionResults ? credential.getClientExtensionResults() : {},
        response: {
          clientDataJSON: bufferToBase64url(response.clientDataJSON),
        },
      };
      if (response.attestationObject) {
        out.response.attestationObject = bufferToBase64url(response.attestationObject);
      }
      if (response.authenticatorData) {
        out.response.authenticatorData = bufferToBase64url(response.authenticatorData);
      }
      if (response.signature) {
        out.response.signature = bufferToBase64url(response.signature);
      }
      if (response.userHandle) {
        out.response.userHandle = bufferToBase64url(response.userHandle);
      }
      return out;
    }

    function showSuccess(text) {
      message.className = 'success';
      message.textContent = text;
      passkeyBtn.hidden = true;
      pinFallback.hidden = true;
      closeAfterSignBtn.hidden = false;
    }

    function showError(text) {
      message.className = 'error';
      message.textContent = text;
    }

    if (!ref) {
      loading.textContent = 'Missing ref query parameter.';
    } else if (!window.PublicKeyCredential) {
      loading.textContent = 'WebAuthn is not available in this browser. Use PIN fallback if enabled.';
    } else {
      fetch('/ts/mandate?ref=' + encodeURIComponent(ref))
        .then((r) => r.json())
        .then((data) => {
          loading.hidden = true;
          if (data.error) {
            loading.hidden = false;
            loading.textContent = data.message || data.error;
            return;
          }
          content.hidden = false;
          document.getElementById('product').textContent = data.display_name || data.item_name || data.item_id || '-';
          document.getElementById('price').textContent = '$' + Number(data.price_cap).toFixed(2) + ' ' + (data.payment_method || 'card').toUpperCase();
          document.getElementById('payment').textContent = (data.payment_method || 'card').toUpperCase();
          document.getElementById('mode').innerHTML = '<span class="badge">' + (data.presence_mode || 'hnp').toUpperCase() + '</span>';
          document.getElementById('ref').textContent = ref;
          pinRequired = !!data.pin_required;
          if (!pinRequired) {
            pinFallback.hidden = true;
          } else if (data.demo_pin) {
            pinHint.hidden = true;
            pinInput.value = String(data.demo_pin);
          } else {
            pinHint.hidden = false;
            pinHint.textContent = 'Enter the PIN shown in the start output.';
          }
        })
        .catch((err) => {
          loading.textContent = 'Failed to load mandate: ' + err;
        });
    }

    passkeyBtn.addEventListener('click', async () => {
      message.textContent = '';
      message.className = '';
      passkeyBtn.disabled = true;
      try {
        const optionsResp = await fetch('/ts/passkey/options?ref=' + encodeURIComponent(ref));
        const optionsData = await optionsResp.json();
        if (!optionsResp.ok || optionsData.error || !optionsData.publicKey) {
          showError(optionsData.message || optionsData.error || 'Could not start passkey flow.');
          passkeyBtn.disabled = false;
          return;
        }

        let credential;
        if (optionsData.op === 'register') {
          const creationOptions = decodeCreationOptions(optionsData.publicKey);
          credential = await navigator.credentials.create({ publicKey: creationOptions });
          message.className = '';
          message.textContent = 'Verifying Touch ID…';
          const payload = { ref, ...credentialToJson(credential) };
          const verifyResp = await fetch('/ts/passkey/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          });
          const verifyData = await verifyResp.json();
          if (verifyData.status === 'ok') {
            showSuccess('Signed — you can return to the chat. The agent will continue checkout.');
          } else {
            showError(verifyData.message || verifyData.error || 'Passkey registration failed.');
            passkeyBtn.disabled = false;
          }
        } else {
          const requestOptions = decodeRequestOptions(optionsData.publicKey);
          credential = await navigator.credentials.get({ publicKey: requestOptions });
          message.className = '';
          message.textContent = 'Verifying Touch ID…';
          const payload = { ref, ...credentialToJson(credential) };
          const verifyResp = await fetch('/ts/passkey/verify', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          });
          const verifyData = await verifyResp.json();
          if (verifyData.status === 'ok') {
            showSuccess('Signed — you can return to the chat. The agent will continue checkout.');
          } else {
            showError(verifyData.message || verifyData.error || 'Passkey verification failed.');
            passkeyBtn.disabled = false;
          }
        }
      } catch (err) {
        showError(String(err));
        passkeyBtn.disabled = false;
      }
    });

    pinConfirmBtn.addEventListener('click', async () => {
      message.textContent = '';
      message.className = '';
      pinConfirmBtn.disabled = true;
      try {
        const body = { ref };
        if (pinInput.value) body.pin = pinInput.value;
        const resp = await fetch('/ts/approve', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        const data = await resp.json();
        if (data.status === 'ok') {
          showSuccess('Signed — you can return to the chat. The agent will continue checkout.');
        } else {
          showError(data.message || data.error || 'PIN approval failed.');
          pinConfirmBtn.disabled = false;
        }
      } catch (err) {
        showError(String(err));
        pinConfirmBtn.disabled = false;
      }
    });
  </script>
</body>
</html>
"""


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
  length = int(handler.headers.get("Content-Length", 0) or 0)
  if length <= 0:
    return {}
  raw = handler.rfile.read(length)
  try:
    data = json.loads(raw.decode("utf-8"))
    if isinstance(data, dict):
      return data
  except (json.JSONDecodeError, UnicodeDecodeError):
    pass
  return {}


def _approve_after_passkey(ref: str, passkey_result: dict[str, Any]) -> dict[str, Any]:
  if passkey_result.get("status") != "ok":
    log_op(_logger, "trusted-surface", "passkey verify failed", result=passkey_result)
    return passkey_result
  approval = confirm_trusted_surface_approval(
      ref,
      pin=os.environ.get("TS_PIN", "").strip() or None,
  )
  if approval.get("status") != "ok":
    log_op(_logger, "trusted-surface", "passkey approval failed", result=approval)
    return approval
  log_op(_logger, "trusted-surface", "passkey approval ok", ref=ref)
  return {
      **passkey_result,
      **approval,
      "message": passkey_result.get("message") or approval.get("message"),
  }


class TrustedSurfaceHandler(BaseHTTPRequestHandler):
  """HTTP handler for H5 Trusted Surface."""

  def log_message(self, format, *args):
    msg = args[0] if args else format
    log_op(_logger, "trusted-surface", "HTTP", message=msg)

  def _cors(self) -> None:
    self.send_header("Access-Control-Allow-Origin", "*")
    self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    self.send_header("Access-Control-Allow-Headers", "Content-Type")

  def do_OPTIONS(self) -> None:
    self.send_response(204)
    self._cors()
    self.end_headers()

  def _json_response(self, status: int, body: dict[str, Any]) -> None:
    payload = json.dumps(body, ensure_ascii=True).encode("utf-8")
    self.send_response(status)
    self.send_header("Content-Type", "application/json")
    self.send_header("Content-Length", str(len(payload)))
    self._cors()
    self.end_headers()
    self.wfile.write(payload)

  def _html_response(self, html: str) -> None:
    payload = html.encode("utf-8")
    self.send_response(200)
    self.send_header("Content-Type", "text/html; charset=utf-8")
    self.send_header("Content-Length", str(len(payload)))
    self._cors()
    self.end_headers()
    self.wfile.write(payload)

  def do_GET(self) -> None:
    parsed = urlparse(self.path)
    qs = parse_qs(parsed.query)
    ref = (qs.get("ref") or [""])[0].strip()

    if parsed.path in ("/", "/health"):
      self._json_response(200, {
          "status": "ok",
          "role": "trusted_surface_unified",
          "endpoints": [
              "POST /ts/sessions",
              "GET /ts/confirm?ref=",
              "GET /ts/mandate?ref=",
              "GET /ts/passkey/options?ref=",
              "POST /ts/passkey/register",
              "POST /ts/passkey/verify",
              "POST /ts/approve",
              "GET /ts/status?ref=",
          ],
      })
      return

    if parsed.path == "/ts/confirm":
      self._html_response(CONFIRM_PAGE_HTML)
      return

    if parsed.path == "/ts/mandate":
      if not ref:
        self._json_response(400, {"error": "ref_required", "message": "ref query param required"})
        return
      draft = get_trusted_surface_draft(ref)
      if not draft:
        self._json_response(404, {
            "error": "not_found",
            "message": "Session not found or expired.",
        })
        return
      pin = os.environ.get("TS_PIN", "").strip()
      draft["pin_required"] = bool(pin)
      if pin and os.environ.get("TS_SHOW_DEMO_PIN", "1").strip() not in ("0", "false", "no"):
        draft["demo_pin"] = pin
      self._json_response(200, draft)
      return

    if parsed.path == "/ts/passkey/options":
      if not ref:
        self._json_response(400, {"error": "ref_required", "message": "ref query param required"})
        return
      result = passkey.build_options(ref)
      status = 200 if "error" not in result else 400
      self._json_response(status, result)
      return

    if parsed.path == "/ts/status":
      if not ref:
        self._json_response(400, {"error": "ref_required", "message": "ref query param required"})
        return
      self._json_response(200, get_ts_session_status(ref))
      return

    self.send_response(404)
    self._cors()
    self.end_headers()

  def do_POST(self) -> None:
    parsed = urlparse(self.path)
    body = _read_json_body(self)

    if parsed.path == "/ts/sessions":
      session_id = str(body.get("session_id", "")).strip()
      price_cap = body.get("price_cap")
      if not session_id or price_cap is None:
        self._json_response(400, {
            "error": "invalid_request",
            "message": "session_id and price_cap are required.",
        })
        return
      result = create_ts_session(
          session_id,
          price_cap=price_cap,
          payment_method=str(body.get("payment_method", "card")),
          item_id=str(body.get("item_id", "")),
          item_name=str(body.get("item_name", "")),
          presence_mode=str(body.get("presence_mode", "hnp")),
          payee=str(body.get("payee", "")),
          constraints=body.get("constraints") if isinstance(body.get("constraints"), dict) else None,
      )
      status = 200 if "error" not in result else 400
      self._json_response(status, result)
      return

    if parsed.path == "/ts/passkey/register":
      ref = str(body.get("ref", "")).strip()
      if not ref:
        self._json_response(400, {"error": "ref_required", "message": "ref is required."})
        return
      result = _approve_after_passkey(ref, passkey.verify_register(ref, body))
      status = 200 if result.get("status") == "ok" else 400
      self._json_response(status, result)
      return

    if parsed.path == "/ts/passkey/verify":
      ref = str(body.get("ref", "")).strip()
      if not ref:
        self._json_response(400, {"error": "ref_required", "message": "ref is required."})
        return
      result = _approve_after_passkey(ref, passkey.verify_assertion(ref, body))
      status = 200 if result.get("status") == "ok" else 400
      self._json_response(status, result)
      return

    if parsed.path == "/ts/approve":
      ref = str(body.get("ref", "")).strip()
      if not ref:
        self._json_response(400, {"error": "ref_required", "message": "ref is required."})
        return
      result = confirm_trusted_surface_approval(
          ref,
          pin=str(body.get("pin", "")) if body.get("pin") is not None else None,
      )
      status = 200 if result.get("status") == "ok" else 400
      self._json_response(status, result)
      return

    self.send_response(404)
    self._cors()
    self.end_headers()


class ReuseHTTPServer(HTTPServer):
  allow_reuse_address = True


if __name__ == "__main__":
  try:
    server = ReuseHTTPServer(("127.0.0.1", PORT), TrustedSurfaceHandler)
  except OSError as e:
    if e.errno == 48:
      print(
          f"Error: Port {PORT} is already in use. "
          f"Kill the process with: lsof -ti:{PORT} | xargs kill -9"
      )
    raise
  print(f"Trusted Surface (H5): http://localhost:{PORT}/")
  print(f"Confirm page example: http://localhost:{PORT}/ts/confirm?ref=<ref>")
  server.serve_forever()
