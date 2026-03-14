/**
 * Normalize loan records from the API into player select options.
 */
export function mapLoansToPlayerOptions(loans = []) {
  return (loans ?? [])
    .map((loan) => {
      const id = loan.player_id ?? loan.player?.id ?? null
      const name =
        loan.player_name ??
        loan.player?.name ??
        loan.player?.full_name ??
        loan.player?.fullname ??
        null

      return { id, name }
    })
    .filter((opt) => opt.id !== null && opt.id !== undefined && !!opt.name)
    .sort((a, b) => a.name.localeCompare(b.name))
}
