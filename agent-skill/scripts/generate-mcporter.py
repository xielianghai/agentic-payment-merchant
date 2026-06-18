#!/usr/bin/env python3
"""Generate mcporter.json for heg-flight (relative repo paths or absolute install paths)."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

SCHEMA = "https://raw.githubusercontent.com/steipete/mcporter/main/mcporter.schema.json"

HTTP_SERVERS = {
    "ap2-buyer": {
        "description": "AP2 buyer: session, mandates, trusted-surface, monitor",
        "baseUrl": "http://127.0.0.1:8100/mcp",
    },
    "ap2-cp": {
        "description": "AP2 mock credentials provider (card + x402)",
        "baseUrl": "http://127.0.0.1:8102/mcp",
    },
    "ap2-mpp": {
        "description": "AP2 mock merchant payment processor",
        "baseUrl": "http://127.0.0.1:8103/mcp",
    },
}

RELATIVE_PATHS = {
    "adapter_mcp": "../../adapter/mcp/server.py",
    "temp_db": "../../payment-stack/.temp-db",
    "heg_mcp": "../../../heg_flight_mock/mcp/server.py",
    "ap2_root": "../../../AP2",
}


def _build_config(
    *,
    adapter_arg: str,
    temp_db: str,
    heg_mcp: str,
    ap2_root: str,
    adapter_base_url: str,
    merchant_mgmt_api: str,
    heg_backend_url: str,
) -> dict:
    return {
        "$schema": SCHEMA,
        "mcpServers": {
            "ap2-merchant-adapter": {
                "description": "Agentic Payment Merchant Adapter (UCP + AP2 flight catalog)",
                "command": "python3",
                "args": [adapter_arg],
                "env": {
                    "ADAPTER_BASE_URL": adapter_base_url,
                    "MERCHANT_MGMT_API": merchant_mgmt_api,
                    "HEG_FLIGHT_BACKEND_URL": heg_backend_url,
                    "HEG_FLIGHT_MCP_SERVER": heg_mcp,
                    "TEMP_DB_DIR": temp_db,
                    "AP2_ROOT": ap2_root,
                },
            },
            **HTTP_SERVERS,
        },
        "imports": [],
    }


def _write_config(path: Path, cfg: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")


def _absolute_paths(merchant_home: Path, args: argparse.Namespace) -> dict[str, str]:
    heg_mcp = args.heg_flight_mcp_server or str(
        (merchant_home.parent / "heg_flight_mock" / "mcp" / "server.py").resolve()
    )
    ap2_root = args.ap2_root or str((merchant_home.parent / "AP2").resolve())
    temp_db = args.temp_db_dir or str((merchant_home / "payment-stack" / ".temp-db").resolve())
    return {
        "adapter_arg": str((merchant_home / "adapter" / "mcp" / "server.py").resolve()),
        "temp_db": temp_db,
        "heg_mcp": os.path.expanduser(heg_mcp),
        "ap2_root": os.path.expanduser(ap2_root),
        "adapter_base_url": args.adapter_base_url,
        "merchant_mgmt_api": args.merchant_mgmt_api,
        "heg_backend_url": args.heg_flight_backend_url,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="Output mcporter.json path")
    parser.add_argument(
        "--mode",
        choices=("relative", "absolute"),
        required=True,
        help="relative: repo skill dirs; absolute: QClaw install with machine paths",
    )
    parser.add_argument(
        "--merchant-home",
        help="Repository root (required for --mode absolute)",
    )
    parser.add_argument(
        "--adapter-base-url",
        default=os.environ.get("ADAPTER_BASE_URL", "http://127.0.0.1:8200"),
    )
    parser.add_argument(
        "--merchant-mgmt-api",
        default=os.environ.get("MERCHANT_MGMT_API", "http://127.0.0.1:9100"),
    )
    parser.add_argument(
        "--heg-flight-backend-url",
        default=os.environ.get("HEG_FLIGHT_BACKEND_URL", "http://127.0.0.1:9000"),
    )
    parser.add_argument(
        "--heg-flight-mcp-server",
        default=os.environ.get("HEG_FLIGHT_MCP_SERVER", ""),
    )
    parser.add_argument(
        "--ap2-root",
        default=os.environ.get("AP2_ROOT", ""),
    )
    parser.add_argument(
        "--temp-db-dir",
        default=os.environ.get("TEMP_DB_DIR", ""),
    )
    args = parser.parse_args()
    out = Path(args.output)

    if args.mode == "relative":
        cfg = _build_config(
            adapter_arg=RELATIVE_PATHS["adapter_mcp"],
            temp_db=RELATIVE_PATHS["temp_db"],
            heg_mcp=RELATIVE_PATHS["heg_mcp"],
            ap2_root=RELATIVE_PATHS["ap2_root"],
            adapter_base_url=args.adapter_base_url,
            merchant_mgmt_api=args.merchant_mgmt_api,
            heg_backend_url=args.heg_flight_backend_url,
        )
    else:
        if not args.merchant_home:
            raise SystemExit("ERROR: --merchant-home is required for --mode absolute")
        merchant_home = Path(args.merchant_home).resolve()
        paths = _absolute_paths(merchant_home, args)
        cfg = _build_config(**paths)

    _write_config(out, cfg)
    print(f"OK  wrote {out} ({args.mode})")


if __name__ == "__main__":
    main()
