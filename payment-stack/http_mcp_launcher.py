#!/usr/bin/env python3
"""Run a unified role FastMCP server over streamable-http (long-lived for openclaw)."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


def main() -> None:
  if len(sys.argv) < 3:
    print(
        "Usage: http_mcp_launcher.py <server.py path> <port> [path=/mcp]",
        file=sys.stderr,
    )
    sys.exit(1)

  server_path = Path(sys.argv[1]).resolve()
  port = int(sys.argv[2])
  mcp_path = sys.argv[3] if len(sys.argv) > 3 else "/mcp"

  if not server_path.is_file():
    print(f"Server not found: {server_path}", file=sys.stderr)
    sys.exit(1)

  roles_dir = server_path.parent.parent
  if roles_dir.name == "roles" and str(roles_dir) not in sys.path:
    sys.path.insert(0, str(roles_dir))

  from path_setup import bootstrap_unified  # noqa: E402

  roles_root = bootstrap_unified(server_path)
  # Buyer/cp/mpp HTTP MCP must share TEMP_DB with trusted_surface_unified (:8104).
  os.environ["TEMP_DB_DIR"] = str(roles_root / ".temp-db")

  spec = importlib.util.spec_from_file_location(
      f"http_mcp_{server_path.stem}", server_path
  )
  if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load {server_path}")
  mod = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(mod)

  mcp = getattr(mod, "mcp", None)
  if mcp is None:
    print(f"No mcp object in {server_path}", file=sys.stderr)
    sys.exit(1)

  host = os.environ.get("AP2_MCP_HOST", "127.0.0.1")
  print(
      f"Starting {server_path.name} streamable-http on http://{host}:{port}{mcp_path}",
      flush=True,
  )
  mcp.run(
      transport="streamable-http",
      host=host,
      port=port,
      path=mcp_path,
      show_banner=False,
  )


if __name__ == "__main__":
  main()
