/** Demo user wallet (matches x402 CP list_wallets / DEFAULT_USER_PRIVATE_KEY). */
export const DEMO_X402_USER_ADDRESS =
    '0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266';

export function maskEthAddress(address: string): string {
  const a = address.trim();
  if (/^0x[a-fA-F0-9]{6}\.\.\.[a-fA-F0-9]{4}$/.test(a)) return a;
  if (!/^0x[a-fA-F0-9]{40}$/.test(a)) return a;
  return `${a.slice(0, 6)}...${a.slice(-4)}`;
}

/** Pull a 0x address from prose or tool description, if present. */
export function extractEthAddress(text: string): string|undefined {
  const full = text.match(/0x[a-fA-F0-9]{40}/);
  if (full) return full[0];
  const masked = text.match(/0x[a-fA-F0-9]{4,6}\.\.\.[a-fA-F0-9]{4}/);
  return masked?.[0];
}

export function formatPaymentDisplay(
    method: 'card'|'x402',
    description?: string,
): {label: string; badge: string} {
  if (method === 'x402') {
    const fromDesc = description ? extractEthAddress(description) : undefined;
    const masked = maskEthAddress(fromDesc ?? DEMO_X402_USER_ADDRESS);
    if (description && /0x/i.test(description)) {
      return {
        label: description.includes('x402') ?
            description.replace(
                /0x[a-fA-F0-9]+(?:\.\.\.[a-fA-F0-9]+)?/,
                masked,
            ) :
            `x402 · ${masked} · USDC (Base Sepolia)`,
        badge: 'USDC (Base Sepolia)',
      };
    }
    return {
      label: `x402 · ${masked} · USDC (Base Sepolia)`,
      badge: 'USDC (Base Sepolia)',
    };
  }
  return {
    label: description || 'Card •••4242',
    badge: 'Default',
  };
}
