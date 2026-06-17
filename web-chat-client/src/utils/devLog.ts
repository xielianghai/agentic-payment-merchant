/**
 * Structured console logging for unified web client (browser devtools).
 * Prefix: [AP2][Role] operation {details}
 */

export function devLog(
    role: string,
    op: string,
    details?: Record<string, unknown>,
): void {
  const suffix =
      details && Object.keys(details).length > 0 ?
      ` ${JSON.stringify(details)}` :
      '';
  console.log(`[AP2][${role}] ${op}${suffix}`);
}

export function devWarn(
    role: string,
    op: string,
    details?: Record<string, unknown>,
): void {
  const suffix =
      details && Object.keys(details).length > 0 ?
      ` ${JSON.stringify(details)}` :
      '';
  console.warn(`[AP2][${role}] ${op}${suffix}`);
}

export function devError(
    role: string,
    op: string,
    details?: Record<string, unknown>,
): void {
  const suffix =
      details && Object.keys(details).length > 0 ?
      ` ${JSON.stringify(details)}` :
      '';
  console.error(`[AP2][${role}] ${op}${suffix}`);
}
