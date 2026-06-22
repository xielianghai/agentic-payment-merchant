"""Constants and standard fallback values for x402 Web3 simulation."""

from __future__ import annotations

from typing import Any

# Standard local development key (Anvil/Hardhat Account 0)
DEFAULT_USER_PRIVATE_KEY = (
    "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
)
DEFAULT_USER_ADDRESS = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"

# Standard merchant receiver (Anvil/Hardhat Account 1)
DEFAULT_MERCHANT_ADDRESS = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"

# Standard facilitator relayer (Anvil/Hardhat Account 2)
DEFAULT_FACILITATOR_PRIVATE_KEY = (
    "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a"
)
DEFAULT_FACILITATOR_ADDRESS = "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC"

# Base Sepolia USDC (used by AP2 x402 PSP / CP on develop)
DEFAULT_USDC_CONTRACT = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"

# Ethereum Sepolia (MetaMask test network)
SEPOLIA_CHAIN_ID = 11155111
X402_NETWORK_NAME = "Sepolia"
X402_NETWORK_SLUG = "sepolia"
X402_TOKEN_SYMBOL = "SepoliaETH"
X402_EIP712_DOMAIN_NAME = "AP2 x402"
X402_EIP712_DOMAIN_VERSION = "1"
# Demo mapping fallback when price feed unavailable (overridden by live quote)
X402_ETH_WEI_PER_CENT = 10**14
DEFAULT_RPC_URL = "https://ethereum-sepolia-rpc.publicnode.com"
SEPOLIA_RPC_ENV = "SEPOLIA_RPC"

# Back-compat alias (was Base Sepolia)
BASE_SEPOLIA_CHAIN_ID = SEPOLIA_CHAIN_ID


def x402_eip712_domain_types() -> list[dict[str, str]]:
  return [
      {"name": "name", "type": "string"},
      {"name": "version", "type": "string"},
      {"name": "chainId", "type": "uint256"},
  ]


def x402_eip712_domain() -> dict[str, Any]:
  return {
      "name": X402_EIP712_DOMAIN_NAME,
      "version": X402_EIP712_DOMAIN_VERSION,
      "chainId": SEPOLIA_CHAIN_ID,
  }
