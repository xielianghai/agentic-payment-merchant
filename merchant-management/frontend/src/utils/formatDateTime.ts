/**
 * Backend stores naive UTC timestamps (e.g. 2026-06-23T09:11:45).
 * Parse as UTC, then render in the browser's local timezone.
 */
export function formatLocalDateTime(
  value?: string | null,
  locale?: string,
): string {
  if (!value) return '—'

  const normalized = value.trim().replace(' ', 'T')
  const hasOffset = normalized.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(normalized)
  const iso = hasOffset ? normalized : `${normalized}Z`
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return value

  return date.toLocaleString(locale || undefined, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
}
