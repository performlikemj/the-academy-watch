// Portable source-tree attestation: evidence-only commits may change HEAD, never app bytes.
import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'
import { spawnSync } from 'node:child_process'
const sha256 = bytes => crypto.createHash('sha256').update(bytes).digest('hex')
function git(appDir, args, binary = false) {
  const result = spawnSync('git', ['-C', appDir, ...args], { encoding: binary ? undefined : 'utf8' })
  if (result.status !== 0) throw new Error(`git ${args[0]} failed`)
  return binary ? result.stdout : result.stdout.trim()
}
export function configDigest(appDir, execution) {
  const keys = ['scheme', 'ui_test_target', 'destination', 'locale', 'timezone', 'appearance', 'dynamic_type', 'grade']
  if (!execution || keys.some(k => typeof execution[k] !== 'string' || !execution[k])) throw new Error('execution configuration missing')
  return sha256(JSON.stringify({ version: 1, harness: sha256(fs.readFileSync(path.join(appDir, 'harness.yaml'))), execution: Object.fromEntries(keys.map(k => [k, execution[k]])) }))
}
export function captureRevision(appDir) {
  const revision = git(appDir, ['rev-parse', 'HEAD'])
  const prefix = git(appDir, ['rev-parse', '--show-prefix']).replace(/\/$/, '')
  const trees = []
  let object = `${revision}^{tree}`
  for (const part of prefix ? prefix.split('/') : []) {
    trees.push(git(appDir, ['cat-file', 'tree', object], true).toString('base64'))
    object = `${object}:${part}`
    // Resolve before traversing another component.
    object = git(appDir, ['rev-parse', object])
  }
  return {
    app_revision: revision,
    source_dirty: Boolean(git(appDir, ['status', '--porcelain', '--untracked-files=all', '--', '.'])),
    app_source_tree: git(appDir, ['rev-parse', object]),
    // Preserve the Git objects needed to verify the original revision even in a fresh clone
    // where an unpushed, evidence-free source commit is not in the final branch history.
    revision_binding: { app_path: prefix, commit: git(appDir, ['cat-file', 'commit', revision], true).toString('base64'), trees },
  }
}
function objectHash(type, bytes, algorithm) {
  return crypto.createHash(algorithm).update(`${type} ${bytes.length}\0`).update(bytes).digest('hex')
}
export function verifyBinding(appDir, report, head) {
  if (!/^(?:[a-f0-9]{40}|[a-f0-9]{64})$/.test(report.app_revision || '')) throw new Error('app_revision missing')
  if (report.source_dirty !== false) throw new Error('report was captured from uncommitted app source')
  const binding = report.revision_binding
  if (!binding || typeof binding.commit !== 'string' || !Array.isArray(binding.trees)) throw new Error('revision binding missing')
  const prefix = git(appDir, ['rev-parse', '--show-prefix']).replace(/\/$/, '')
  if (binding.app_path !== prefix) throw new Error('revision app path mismatch')
  const algorithm = report.app_revision.length === 40 ? 'sha1' : 'sha256'
  const commit = Buffer.from(binding.commit, 'base64')
  if (objectHash('commit', commit, algorithm) !== report.app_revision) throw new Error('revision commit digest mismatch')
  let tree = /^tree ([a-f0-9]+)\n/.exec(commit.toString())?.[1]
  const parts = prefix ? prefix.split('/') : []
  if (parts.length !== binding.trees.length) throw new Error('revision tree chain mismatch')
  parts.forEach((part, i) => {
    const bytes = Buffer.from(binding.trees[i], 'base64')
    if (objectHash('tree', bytes, algorithm) !== tree) throw new Error('revision tree digest mismatch')
    let offset = 0, found
    while (offset < bytes.length) {
      const zero = bytes.indexOf(0, offset)
      if (zero < 0) throw new Error('invalid git tree')
      const entry = bytes.subarray(offset, zero).toString()
      const hashEnd = zero + 1 + report.app_revision.length / 2
      if (entry === `40000 ${part}`) found = bytes.subarray(zero + 1, hashEnd).toString('hex')
      offset = hashEnd
    }
    if (!found) throw new Error('app directory missing from revision tree')
    tree = found
  })
  const headTree = git(appDir, ['rev-parse', prefix ? `${head}:${prefix}` : `${head}^{tree}`])
  if (tree !== report.app_source_tree || tree !== headTree) throw new Error('app source tree does not match app HEAD')
  if (git(appDir, ['status', '--porcelain', '--untracked-files=all', '--', '.'])) throw new Error('app source has uncommitted changes')
  if (report.config_digest !== configDigest(appDir, report.execution_config)) throw new Error('config_digest does not match sim configuration')
  return report.app_revision === head ? 'exact revision' : 'source-tree equivalent revision'
}
