"""Ensure ap2-samples src package (common, roles) is importable from unified roles."""

import sys
from pathlib import Path


def ensure_common_overrides_on_path() -> Path:
  """Insert local common/ overrides before AP2 src (x402 MetaMask on develop)."""
  overrides = Path(__file__).resolve().parent / "ap2_common_overrides"
  return overrides


def ensure_src_on_path() -> Path:
  """Insert AP2 code/samples/python/src on sys.path."""
  import os

  ap2_root = Path(os.environ.get("AP2_ROOT", "")).expanduser()
  if not ap2_root.is_dir():
    # payment-stack/ -> agentic-payment-merchant/ -> payment/AP2
    ap2_root = Path(__file__).resolve().parents[1].parent / "AP2"
  ap2_samples = ap2_root / "code" / "samples" / "python" / "src"
  src_str = str(ap2_samples)
  overrides_str = str(ensure_common_overrides_on_path())
  for path in (src_str, overrides_str):
    while path in sys.path:
      sys.path.remove(path)
  # Local x402 helpers must precede AP2 src so namespace common/ merges correctly.
  sys.path.insert(0, src_str)
  sys.path.insert(0, overrides_str)
  return ap2_samples


def find_unified_roles_root(entry_file: str | Path) -> Path:
  """Locate payment-stack root from any file under it."""
  p = Path(entry_file).resolve()
  for parent in (p.parent, *p.parents):
    if (parent / "path_setup.py").is_file() and (parent / "shopping_agent_unified").is_dir():
      return parent
  raise RuntimeError(f"payment-stack root not found from {entry_file}")


def bootstrap_unified(entry_file: str | Path) -> Path:
  """Add src/ first, unified roles/ last — avoids shadowing the src roles package."""
  roles_root = find_unified_roles_root(entry_file)
  ensure_src_on_path()
  roles_str = str(roles_root)
  if roles_str not in sys.path:
    sys.path.append(roles_str)
  return roles_root


def resolve_ap2_root() -> Path:
  """Return AP2 checkout root (workspace for uv / ap2-samples)."""
  import os

  ap2_root = Path(os.environ.get("AP2_ROOT", "")).expanduser()
  if ap2_root.is_dir():
    return ap2_root
  return Path(__file__).resolve().parents[1].parent / "AP2"


def resolve_heg_mcp_server() -> Path:
  """HEG flight MCP entrypoint (env override or sibling heg_flight_mock repo)."""
  import os

  env_path = os.environ.get("HEG_FLIGHT_MCP_SERVER", "").strip()
  if env_path:
    return Path(env_path).expanduser().resolve()
  demo_root = Path(__file__).resolve().parents[1].parent
  return (demo_root.parent / "heg_flight_mock" / "mcp" / "server.py").resolve()
