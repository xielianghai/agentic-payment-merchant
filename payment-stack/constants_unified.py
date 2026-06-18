"""Constants for the unified AP2 demo (does not modify src/common/constants.py)."""

import os
from pathlib import Path


_UNIFIED_ROOT = Path(__file__).resolve().parent
DEFAULT_TEMP_DB = _UNIFIED_ROOT / ".temp-db"
DEFAULT_LOGS = _UNIFIED_ROOT / ".logs"

TEMP_DB = Path(os.environ.get("TEMP_DB_DIR", str(DEFAULT_TEMP_DB)))
LOGS_DIR = Path(os.environ.get("LOGS_DIR", str(DEFAULT_LOGS)))

USER_SIGNING_KEY_PATH = Path(
    os.environ.get(
        "USER_SIGNING_KEY_PATH",
        str(TEMP_DB / "user_signing_key.pem"),
    )
)
USER_SIGNING_PUB_PATH = Path(
    os.environ.get(
        "USER_SIGNING_PUB_PATH",
        str(TEMP_DB / "user_signing_key.pub"),
    )
)

AGENT_PORT = int(os.environ.get("UNIFIED_AGENT_PORT", "8090"))
MERCHANT_TRIGGER_PORT = int(os.environ.get("UNIFIED_MERCHANT_TRIGGER_PORT", "8091"))
CP_TRIGGER_PORT = int(os.environ.get("UNIFIED_CP_TRIGGER_PORT", "8092"))
MPP_TRIGGER_PORT = int(os.environ.get("UNIFIED_MPP_TRIGGER_PORT", "8093"))
X402_PSP_TRIGGER_PORT = int(os.environ.get("UNIFIED_X402_PSP_TRIGGER_PORT", "8094"))
WEB_CLIENT_PORT = int(os.environ.get("UNIFIED_WEB_CLIENT_PORT", "5183"))

# Long-lived HTTP MCP servers for openclaw (mcporter streamable-http)
BUYER_MCP_PORT = int(os.environ.get("UNIFIED_BUYER_MCP_PORT", "8100"))
MERCHANT_MCP_PORT = int(os.environ.get("UNIFIED_MERCHANT_MCP_PORT", "8101"))
CP_MCP_PORT = int(os.environ.get("UNIFIED_CP_MCP_PORT", "8102"))
MPP_MCP_PORT = int(os.environ.get("UNIFIED_MPP_MCP_PORT", "8103"))
TRUSTED_SURFACE_PORT = int(os.environ.get("UNIFIED_TRUSTED_SURFACE_PORT", "8104"))
TRUSTED_SURFACE_BASE_URL = os.environ.get(
    "TS_BASE_URL",
    f"http://localhost:{TRUSTED_SURFACE_PORT}",
)
MONITOR_SCHEDULER_PORT = int(
    os.environ.get("UNIFIED_MONITOR_SCHEDULER_PORT", "8105")
)
MONITOR_SCHEDULER_BASE_URL = os.environ.get(
    "MONITOR_SCHEDULER_BASE_URL",
    f"http://localhost:{MONITOR_SCHEDULER_PORT}",
)

MPP_INITIATE_PAYMENT_URL = (
    f"http://127.0.0.1:{MPP_TRIGGER_PORT}/initiate-payment"
)
CP_PAYMENT_RECEIPT_URL = f"http://127.0.0.1:{CP_TRIGGER_PORT}/payment-receipt"
X402_SETTLE_PAYMENT_URL = f"http://127.0.0.1:{X402_PSP_TRIGGER_PORT}/settle-payment"

SUPPORTED_PAYMENT_METHODS = frozenset({"card", "x402"})
SUPPORTED_PRESENCE_MODES = frozenset({"hp", "hnp"})
