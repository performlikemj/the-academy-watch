/**
 * Build query params for fetching team loans for the writer editor.
 * Ensures we pull the current season and include supplemental/manual rows.
 * @param {{ direction?: 'loaned_from' | 'loaned_to' }} options
 * @returns {{active_only: string, dedupe: string, include_supplemental: string, direction?: string}}
 */
export function buildLoanFetchParams(options = {}) {
  const params = {
    active_only: 'true',
    dedupe: 'true',
    include_supplemental: 'true',
  }

  if (options.direction) {
    params.direction = options.direction
  }

  return params
}
