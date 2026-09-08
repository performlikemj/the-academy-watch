import { test } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { execFileSync } from 'node:child_process'
import { captureRevision, configDigest, verifyBinding } from './ios-proof-binding.mjs'

test('source/config binding survives an evidence-only commit and fresh clone, rejects drift and tampering', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ios-binding-'))
  try {
    const repo = path.join(root, 'repo'), app = path.join(repo, 'app')
    fs.mkdirSync(app, { recursive: true })
    const git = (...args) => execFileSync('git', ['-C', repo, ...args], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim()
    git('init'); git('config', 'user.name', 'Proof test'); git('config', 'user.email', 'proof@example.test')
    fs.writeFileSync(path.join(repo, 'base'), 'base'); git('add', 'base'); git('commit', '-m', 'base')
    const base = git('rev-parse', 'HEAD')
    fs.writeFileSync(path.join(app, 'harness.yaml'), 'sim:\n  grade: false\n')
    fs.writeFileSync(path.join(app, 'source.swift'), 'source')
    git('add', 'app/harness.yaml', 'app/source.swift'); git('commit', '-m', 'source')
    const execution = { scheme: 'Offline', ui_test_target: 'UITests', destination: 'iOS', locale: 'en', timezone: 'UTC', appearance: 'light', dynamic_type: 'default', grade: '0' }
    const report = { ...captureRevision(app), execution_config: execution, config_digest: configDigest(app, execution) }
    assert.equal(verifyBinding(app, report, git('rev-parse', 'HEAD')), 'exact revision')
    // Replace only the unpushed source commit with one final source+evidence commit.
    git('reset', '--soft', base)
    fs.writeFileSync(path.join(repo, 'evidence.json'), JSON.stringify(report)); git('add', 'evidence.json'); git('commit', '-m', 'source and evidence')
    const head = git('rev-parse', 'HEAD')
    assert.equal(verifyBinding(app, report, head), 'source-tree equivalent revision')
    const clone = path.join(root, 'clone')
    execFileSync('git', ['clone', '--no-local', repo, clone], { stdio: 'pipe' })
    assert.equal(verifyBinding(path.join(clone, 'app'), report, head), 'source-tree equivalent revision')
    assert.throws(() => verifyBinding(app, { ...report, config_digest: '0'.repeat(64) }, head), /config_digest/)
    assert.throws(() => verifyBinding(app, { ...report, config_digest: undefined }, head), /config_digest/)
    assert.throws(() => verifyBinding(app, { ...report, source_dirty: true }, head), /uncommitted/)
    assert.throws(() => verifyBinding(app, { ...report, revision_binding: { ...report.revision_binding, commit: Buffer.from('forged').toString('base64') } }, head), /commit digest/)
    assert.throws(() => verifyBinding(app, { ...report, revision_binding: { ...report.revision_binding, trees: ['Zm9yZ2Vk'] } }, head), /tree digest/)
    fs.writeFileSync(path.join(app, 'extra.swift'), 'untracked source')
    assert.throws(() => verifyBinding(app, report, head), /uncommitted/)
    fs.unlinkSync(path.join(app, 'extra.swift'))
    fs.appendFileSync(path.join(app, 'source.swift'), 'changed'); git('add', 'app/source.swift'); git('commit', '-m', 'changed source')
    assert.throws(() => verifyBinding(app, report, git('rev-parse', 'HEAD')), /source tree/)
    assert.notEqual(configDigest(app, { ...execution, scheme: 'Live' }), report.config_digest)
    fs.appendFileSync(path.join(app, 'harness.yaml'), '# drift')
    assert.notEqual(configDigest(app, execution), report.config_digest)
  } finally { fs.rmSync(root, { recursive: true, force: true }) }
})
