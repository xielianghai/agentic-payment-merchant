"""Unified shopping agent package — path bootstrap before ADK loads agent.py."""

import importlib.util
import sys
from pathlib import Path


def _bootstrap() -> None:
  entry = Path(__file__).resolve()
  roles_root = entry.parents[2]
  spec = importlib.util.spec_from_file_location(
      "unified_path_setup", roles_root / "path_setup.py"
  )
  if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load path_setup from {roles_root}")
  mod = importlib.util.module_from_spec(spec)
  sys.modules["unified_path_setup"] = mod
  spec.loader.exec_module(mod)
  mod.bootstrap_unified(entry)


_bootstrap()


def __getattr__(name: str):
  if name == "root_agent":
    from shopping_agent.agent import root_agent
    return root_agent
  raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["root_agent"]
