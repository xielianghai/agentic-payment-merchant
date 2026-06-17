"""User signing key for HP Trusted Surface (unified demo)."""

import json
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import ec
from jwcrypto.jwk import JWK

from path_setup import bootstrap_unified  # noqa: E402

bootstrap_unified(__file__)
from constants_unified import USER_SIGNING_KEY_PATH, USER_SIGNING_PUB_PATH  # noqa: E402


def get_or_create_user_signing_key() -> JWK:
  """Load or generate ES256 user key (simulates Trusted Surface)."""
  if USER_SIGNING_KEY_PATH.exists():
    return JWK.from_json(USER_SIGNING_KEY_PATH.read_text(encoding="utf-8"))
  raw_key = ec.generate_private_key(ec.SECP256R1())
  key = JWK.from_pyca(raw_key)
  jwk_dict = json.loads(key.export())
  jwk_dict["kid"] = "user-signing-key-1"
  key = JWK.from_json(json.dumps(jwk_dict))
  USER_SIGNING_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
  USER_SIGNING_KEY_PATH.write_text(key.export(), encoding="utf-8")
  USER_SIGNING_PUB_PATH.write_text(key.export_public(), encoding="utf-8")
  return key
