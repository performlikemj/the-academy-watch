export function seedSelectedButtonLabel({ isSeeding, selectionCount }) {
  if (isSeeding) {
    if (selectionCount > 1) return `Seeding ${selectionCount} teams...`
    return 'Seeding team...'
  }
  return 'Seed Selected Teams'
}

export function seedTop5ButtonLabel({ isSeeding, dryRun }) {
  if (isSeeding) return 'Seeding top-5...'
  return dryRun ? 'Preview Seeding' : 'Seed Top-5 Leagues'
}

// buildMissingNamesParams / buildBackfillNamesPayload were removed along with
// the broken Missing Names section in AdminNewsletters — they targeted
// APIService.adminMissingNames/adminBackfillNames, which no longer exist
// (legacy loan endpoints). Name backfill now lives at
// POST /api/admin/players/backfill-names (Operations page).
