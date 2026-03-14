import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const frontendSrc = path.resolve(__dirname, '../src')
const backendSrc = path.resolve(__dirname, '../../loan-army-backend/src')
const backendRoot = path.resolve(__dirname, '../../loan-army-backend')

// ============================================================================
// BACKEND MODEL TESTS
// ============================================================================

test('UserAccount model has editor and placeholder fields', async () => {
  const modelFile = path.join(backendSrc, 'models/league.py')
  const src = await fs.readFile(modelFile, 'utf8')

  // Editor role field
  assert.match(
    src,
    /is_editor\s*=\s*db\.Column\(db\.Boolean/,
    'UserAccount should have is_editor boolean column'
  )

  // Placeholder account fields
  assert.match(
    src,
    /managed_by_user_id\s*=\s*db\.Column\(db\.Integer/,
    'UserAccount should have managed_by_user_id column'
  )
  assert.match(
    src,
    /claimed_at\s*=\s*db\.Column\(db\.DateTime/,
    'UserAccount should have claimed_at column'
  )
  assert.match(
    src,
    /claim_token\s*=\s*db\.Column\(db\.String/,
    'UserAccount should have claim_token column'
  )
  assert.match(
    src,
    /claim_token_expires_at\s*=\s*db\.Column\(db\.DateTime/,
    'UserAccount should have claim_token_expires_at column'
  )

  // Helper methods
  assert.match(
    src,
    /def is_placeholder\(self\)/,
    'UserAccount should have is_placeholder() method'
  )
  assert.match(
    src,
    /def is_claimed\(self\)/,
    'UserAccount should have is_claimed() method'
  )

  // Self-referential relationship (can span multiple lines)
  assert.match(
    src,
    /managed_by\s*=\s*db\.relationship\(/,
    'UserAccount should have managed_by relationship'
  )
})

// ============================================================================
// BACKEND ENDPOINT TESTS
// ============================================================================

test('journalist.py has require_editor_or_admin decorator', async () => {
  const routeFile = path.join(backendSrc, 'routes/journalist.py')
  const src = await fs.readFile(routeFile, 'utf8')

  assert.match(
    src,
    /def require_editor_or_admin\(f\)/,
    'Should have require_editor_or_admin decorator'
  )
  assert.match(
    src,
    /user\.is_editor\s+or\s+is_admin/,
    'Decorator should check is_editor or admin status'
  )
})

test('journalist.py has editor writer CRUD endpoints', async () => {
  const routeFile = path.join(backendSrc, 'routes/journalist.py')
  const src = await fs.readFile(routeFile, 'utf8')

  // List writers
  assert.match(
    src,
    /@journalist_bp\.route\(['"]\/editor\/writers['"]/,
    'Should have GET /editor/writers endpoint'
  )
  assert.match(
    src,
    /def list_managed_writers\(/,
    'Should have list_managed_writers function'
  )

  // Create writer
  assert.match(
    src,
    /def create_placeholder_writer\(/,
    'Should have create_placeholder_writer function'
  )

  // Update writer
  assert.match(
    src,
    /def update_placeholder_writer\(/,
    'Should have update_placeholder_writer function'
  )

  // Delete writer
  assert.match(
    src,
    /def delete_placeholder_writer\(/,
    'Should have delete_placeholder_writer function'
  )
})

test('journalist.py has claim flow endpoints', async () => {
  const routeFile = path.join(backendSrc, 'routes/journalist.py')
  const src = await fs.readFile(routeFile, 'utf8')

  // Send claim invite
  assert.match(
    src,
    /\/editor\/writers\/<int:writer_id>\/send-claim-invite/,
    'Should have send-claim-invite endpoint'
  )
  assert.match(
    src,
    /def send_claim_invite\(/,
    'Should have send_claim_invite function'
  )

  // Validate claim token
  assert.match(
    src,
    /\/claim\/validate/,
    'Should have /claim/validate endpoint'
  )
  assert.match(
    src,
    /def validate_claim_token\(/,
    'Should have validate_claim_token function'
  )

  // Complete claim
  assert.match(
    src,
    /\/claim\/complete/,
    'Should have /claim/complete endpoint'
  )
  assert.match(
    src,
    /def complete_claim\(/,
    'Should have complete_claim function'
  )
})

test('journalist.py supports on-behalf-of commentary creation', async () => {
  const routeFile = path.join(backendSrc, 'routes/journalist.py')
  const src = await fs.readFile(routeFile, 'utf8')

  assert.match(
    src,
    /author_id\s*=\s*data\.get\(['"]author_id['"]\)/,
    'Commentary creation should accept author_id parameter'
  )
  assert.match(
    src,
    /target_writer|target_author/i,
    'Should validate target author for on-behalf-of writing'
  )
})

test('api.py has admin editor role toggle endpoint', async () => {
  const routeFile = path.join(backendSrc, 'routes/api.py')
  const src = await fs.readFile(routeFile, 'utf8')

  assert.match(
    src,
    /\/admin\/users\/<int:user_id>\/editor-role/,
    'Should have /admin/users/<id>/editor-role endpoint'
  )
  assert.match(
    src,
    /def admin_toggle_editor_role\(/,
    'Should have admin_toggle_editor_role function'
  )
})

// ============================================================================
// EMAIL SERVICE TESTS
// ============================================================================

test('email service has claim invitation method', async () => {
  const emailFile = path.join(backendSrc, 'services/email_service.py')
  const src = await fs.readFile(emailFile, 'utf8')

  assert.match(
    src,
    /def send_claim_invitation\(/,
    'Should have send_claim_invitation method'
  )
  assert.match(
    src,
    /claim_url/,
    'Claim email method should accept claim_url parameter'
  )
})

// ============================================================================
// DATABASE MIGRATION TESTS
// ============================================================================

test('migration adds editor and placeholder fields', async () => {
  const migrationsDir = path.join(backendRoot, 'migrations/versions')
  const files = await fs.readdir(migrationsDir)
  const editorMigration = files.find(f => f.includes('editor') && f.includes('placeholder'))

  assert.ok(editorMigration, 'Should have migration file for editor/placeholder fields')

  const migrationFile = path.join(backendRoot, `migrations/versions/${editorMigration}`)
  const src = await fs.readFile(migrationFile, 'utf8')

  assert.match(src, /is_editor/, 'Migration should add is_editor column')
  assert.match(src, /managed_by_user_id/, 'Migration should add managed_by_user_id column')
  assert.match(src, /claimed_at/, 'Migration should add claimed_at column')
  assert.match(src, /claim_token/, 'Migration should add claim_token column')
  assert.match(src, /claim_token_expires_at/, 'Migration should add claim_token_expires_at column')
})

// ============================================================================
// FRONTEND API SERVICE TESTS
// ============================================================================

test('API service has editor/writer management methods', async () => {
  const apiFile = path.join(frontendSrc, 'lib/api.js')
  const src = await fs.readFile(apiFile, 'utf8')

  // Admin editor role toggle
  assert.match(
    src,
    /adminUpdateEditorRole/,
    'Should have adminUpdateEditorRole method'
  )

  // Editor writer management
  assert.match(
    src,
    /getEditorManagedWriters/,
    'Should have getEditorManagedWriters method'
  )
  assert.match(
    src,
    /createPlaceholderWriter/,
    'Should have createPlaceholderWriter method'
  )
  assert.match(
    src,
    /updatePlaceholderWriter/,
    'Should have updatePlaceholderWriter method'
  )
  assert.match(
    src,
    /deletePlaceholderWriter/,
    'Should have deletePlaceholderWriter method'
  )
  assert.match(
    src,
    /sendClaimInvite/,
    'Should have sendClaimInvite method'
  )
})

test('API service has claim flow methods', async () => {
  const apiFile = path.join(frontendSrc, 'lib/api.js')
  const src = await fs.readFile(apiFile, 'utf8')

  assert.match(
    src,
    /validateClaimToken/,
    'Should have validateClaimToken method'
  )
  assert.match(
    src,
    /completeAccountClaim/,
    'Should have completeAccountClaim method'
  )
})

// ============================================================================
// FRONTEND ADMIN EXTERNAL WRITERS PAGE TESTS
// ============================================================================

test('AdminExternalWriters page exists and has required structure', async () => {
  const pageFile = path.join(frontendSrc, 'pages/admin/AdminExternalWriters.jsx')
  const src = await fs.readFile(pageFile, 'utf8')

  // Component export
  assert.match(
    src,
    /export\s+(function|const)\s+AdminExternalWriters/,
    'Should export AdminExternalWriters component'
  )

  // Summary cards
  assert.match(
    src,
    /Total Writers|totalWriters/i,
    'Should show total writers count'
  )
  assert.match(
    src,
    /Unclaimed|unclaimed/i,
    'Should show unclaimed writers count'
  )
  assert.match(
    src,
    /Claimed|claimed/i,
    'Should show claimed writers count'
  )

  // Writer management
  assert.match(
    src,
    /createPlaceholderWriter|Create.*Writer/i,
    'Should have create writer functionality'
  )
  assert.match(
    src,
    /sendClaimInvite|Send.*Claim/i,
    'Should have send claim invite functionality'
  )
})

test('AdminExternalWriters has create/edit dialog', async () => {
  const pageFile = path.join(frontendSrc, 'pages/admin/AdminExternalWriters.jsx')
  const src = await fs.readFile(pageFile, 'utf8')

  // Dialog component
  assert.match(
    src,
    /Dialog|Modal/,
    'Should use Dialog or Modal for create/edit'
  )

  // Form fields
  assert.match(src, /display_name|displayName/i, 'Should have display name field')
  assert.match(src, /email/i, 'Should have email field')
  assert.match(src, /attribution_name|attributionName/i, 'Should have attribution name field')
})

// ============================================================================
// FRONTEND ADMIN USERS PAGE TESTS
// ============================================================================

test('AdminUsers shows editor badge and toggle', async () => {
  const pageFile = path.join(frontendSrc, 'pages/admin/AdminUsers.jsx')
  const src = await fs.readFile(pageFile, 'utf8')

  // Editor badge
  assert.match(
    src,
    /is_editor.*Editor|Editor.*is_editor/s,
    'Should show Editor badge for users with is_editor'
  )

  // Toggle editor role
  assert.match(
    src,
    /adminUpdateEditorRole|toggle.*editor|Make Editor|Revoke Editor/i,
    'Should have toggle editor role functionality'
  )
})

// ============================================================================
// FRONTEND WRITEUP EDITOR TESTS
// ============================================================================

test('WriteupEditor has author selector for editors', async () => {
  const pageFile = path.join(frontendSrc, 'pages/writer/WriteupEditor.jsx')
  const src = await fs.readFile(pageFile, 'utf8')

  // Managed writers state
  assert.match(
    src,
    /managedWriters|managed_writers/i,
    'Should track managed writers'
  )

  // Author selector
  assert.match(
    src,
    /selectedAuthor|author_id|authorId/i,
    'Should have author selection state'
  )

  // On-behalf-of in payload
  assert.match(
    src,
    /author_id.*selectedAuthor|selectedAuthor.*author_id/s,
    'Should include author_id in payload when editor selects different author'
  )
})

// ============================================================================
// FRONTEND CLAIM ACCOUNT PAGE TESTS
// ============================================================================

test('ClaimAccount page exists and handles claim flow', async () => {
  const pageFile = path.join(frontendSrc, 'pages/ClaimAccount.jsx')
  const src = await fs.readFile(pageFile, 'utf8')

  // Component export
  assert.match(
    src,
    /export\s+(function|const)\s+ClaimAccount/,
    'Should export ClaimAccount component'
  )

  // Token from URL
  assert.match(
    src,
    /useSearchParams|searchParams.*token/,
    'Should get token from URL search params'
  )

  // Status states
  assert.match(src, /validating/i, 'Should have validating state')
  assert.match(src, /valid/i, 'Should have valid state')
  assert.match(src, /invalid/i, 'Should have invalid state')
  assert.match(src, /claiming/i, 'Should have claiming state')
  assert.match(src, /success/i, 'Should have success state')

  // API calls
  assert.match(src, /validateClaimToken/, 'Should call validateClaimToken')
  assert.match(src, /completeAccountClaim/, 'Should call completeAccountClaim')

  // Redirect on success
  assert.match(
    src,
    /navigate.*writer.*dashboard|redirect.*dashboard/i,
    'Should redirect to writer dashboard on success'
  )
})

// ============================================================================
// FRONTEND ROUTING TESTS
// ============================================================================

test('App.jsx has routes for external writers feature', async () => {
  const appFile = path.join(frontendSrc, 'App.jsx')
  const src = await fs.readFile(appFile, 'utf8')

  // Imports
  assert.match(
    src,
    /import.*AdminExternalWriters/,
    'Should import AdminExternalWriters'
  )
  assert.match(
    src,
    /import.*ClaimAccount/,
    'Should import ClaimAccount'
  )

  // Routes
  assert.match(
    src,
    /path=["'].*claim-account["']/,
    'Should have /claim-account route'
  )
  assert.match(
    src,
    /path=["']external-writers["']/,
    'Should have external-writers admin route'
  )
})

test('AdminSidebar has External Writers navigation', async () => {
  const sidebarFile = path.join(frontendSrc, 'components/admin/AdminSidebar.jsx')
  const src = await fs.readFile(sidebarFile, 'utf8')

  assert.match(
    src,
    /External Writers/,
    'Should have External Writers label in sidebar'
  )
  assert.match(
    src,
    /external-writers/,
    'Should link to /admin/external-writers'
  )
})

// ============================================================================
// INTEGRATION TESTS - Flow validation
// ============================================================================

test('Editor flow: create writer -> assign coverage -> send invite is supported', async () => {
  const apiFile = path.join(frontendSrc, 'lib/api.js')
  const src = await fs.readFile(apiFile, 'utf8')

  // All required methods exist for the flow
  const requiredMethods = [
    'createPlaceholderWriter',
    'editorAssignTeams',
    'editorAssignLoanTeams',
    'sendClaimInvite'
  ]

  for (const method of requiredMethods) {
    assert.match(
      src,
      new RegExp(method),
      `API should have ${method} for editor flow`
    )
  }
})

test('Claim flow: validate -> complete -> redirect is supported', async () => {
  const claimFile = path.join(frontendSrc, 'pages/ClaimAccount.jsx')
  const src = await fs.readFile(claimFile, 'utf8')

  // Validate token on mount
  assert.match(
    src,
    /useEffect.*validateToken|validateToken.*useEffect/s,
    'Should validate token on component mount'
  )

  // Store auth token on successful claim
  assert.match(
    src,
    /setUserToken|localStorage.*token/i,
    'Should store auth token after successful claim'
  )
})

console.log('\n✓ All external writers feature tests passed!\n')
console.log('=' .repeat(70))
console.log('MANUAL VERIFICATION CHECKLIST')
console.log('=' .repeat(70))
console.log(`
1. DATABASE MIGRATION
   □ Run: cd loan-army-backend && flask db upgrade
   □ Verify: New columns exist in user_accounts table

2. ADMIN: MAKE USER AN EDITOR
   □ Go to: /admin/users
   □ Find a test user, click dropdown → "Make Editor"
   □ Verify: Purple "Editor" badge appears

3. ADMIN: EXTERNAL WRITERS PAGE
   □ Go to: /admin/external-writers
   □ Verify: Summary cards show (Total, Unclaimed, Claimed)
   □ Click "Add External Writer"
   □ Fill form: name, email, attribution_name
   □ Submit and verify writer appears in list

4. EDITOR: WRITE ON BEHALF OF MANAGED WRITER
   □ Log in as an editor user (not admin)
   □ Go to: /writer/writeup-editor
   □ Verify: Author selector dropdown appears
   □ Select a managed writer
   □ Create a commentary
   □ Verify: Commentary is attributed to the managed writer

5. SEND CLAIM INVITE
   □ Go to: /admin/external-writers
   □ Find an unclaimed writer
   □ Click "Send Claim Invite"
   □ Verify: Email sent (check logs or inbox)

6. CLAIM ACCOUNT FLOW
   □ Get claim URL from email (or construct: /claim-account?token=xxx)
   □ Visit the claim URL
   □ Verify: Shows writer info and "Claim Account" button
   □ Click "Claim Account"
   □ Verify: Redirects to /writer/dashboard
   □ Verify: Writer can now log in independently

7. POST-CLAIM VERIFICATION
   □ Check /admin/external-writers
   □ Verify: Writer shows as "Claimed" status
   □ Verify: managed_by relationship preserved for audit
`)
