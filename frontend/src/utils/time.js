export function formatWithTimezone(timestamp, timezone, options = {}) {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) return String(timestamp)

  try {
    return new Intl.DateTimeFormat(undefined, {
      timeZone: timezone || 'Asia/Shanghai',
      ...options,
    }).format(date)
  } catch (_) {
    return date.toLocaleString()
  }
}

export function formatTimeWithTimezone(timestamp, timezone) {
  return formatWithTimezone(timestamp, timezone, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
}

export function formatDateTimeWithTimezone(timestamp, timezone) {
  return formatWithTimezone(timestamp, timezone, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
}

export function formatSortableDateTimeWithTimezone(timestamp, timezone) {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) return String(timestamp)

  try {
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone: timezone || 'Asia/Shanghai',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }).formatToParts(date)
    const part = (type) => parts.find((item) => item.type === type)?.value || ''
    return `${part('year')}-${part('month')}-${part('day')} ${part('hour')}:${part('minute')}:${part('second')}`
  } catch (_) {
    return date.toLocaleString()
  }
}
