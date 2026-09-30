// Mirrored from src/models/interest.py; test_interest.py asserts exact parity.
export const INTEREST_FEATURES = [
  'early_access', 'clubs_near_you', 'opportunities',
  'player_applications', 'recruiting', 'club_staff',
]
export const INTEREST_ROLES = ['club', 'player', 'parent', 'scout', 'coach', 'other']
export const interestLabel = (value) => value.replaceAll('_', ' ').replace(/^./, (letter) => letter.toUpperCase())
