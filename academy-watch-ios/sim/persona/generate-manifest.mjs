#!/usr/bin/env node

import crypto from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'

function usage() {
  console.log('Usage: generate-manifest.mjs <persona.md> <output.json> [--include <Y-001,Y-002,...>]')
}

const args = process.argv.slice(2)
if (args.includes('-h') || args.includes('--help')) { usage(); process.exit(0) }
if (args.length !== 2 && args.length !== 4) { usage(); process.exit(2) }
if (args.length === 4 && args[2] !== '--include') { usage(); process.exit(2) }

const sourcePath = path.resolve(args[0])
const outputPath = path.resolve(args[1])
const markdown = fs.readFileSync(sourcePath, 'utf8')
const version = markdown.match(/^version:\s*([^\s]+)\s*$/m)?.[1]
if (!version) throw new Error('persona front matter must declare version')

const facts = []
for (const [index, line] of markdown.split(/\r?\n/).entries()) {
  if (!line.startsWith('- Y-')) continue
  const match = line.match(/^- (Y-[0-9]{3}) \| status: (confirmed|proposed) \| citation: `([^`]+)` \| (.+)$/)
  if (!match) throw new Error(`malformed persona fact at line ${index + 1}`)
  facts.push({ id: match[1], status: match[2], citation: match[3], text: match[4] })
}
if (!facts.length) throw new Error('persona contains no facts')
if (new Set(facts.map((fact) => fact.id)).size !== facts.length) throw new Error('persona fact ids must be unique')

let selected = facts.filter((fact) => fact.status === 'confirmed')
if (args.length === 4) {
  const requested = args[3].split(',').filter(Boolean)
  const requestedFacts = requested.map((id) => facts.find((fact) => fact.id === id))
  const missing = requested.filter((_, index) => !requestedFacts[index])
  if (missing.length) throw new Error(`unknown persona fact id: ${missing.join(', ')}`)
  const proposed = requestedFacts.filter((fact) => fact.status === 'proposed').map((fact) => fact.id)
  if (proposed.length) throw new Error(`refusing proposed persona fact id: ${proposed.join(', ')}`)
  selected = requestedFacts
}

const manifest = {
  persona: 'yuki',
  persona_version: version,
  persona_digest: crypto.createHash('sha256').update(markdown).digest('hex'),
  facts: selected.map(({ id, citation, text }) => ({ id, citation, text })),
}
fs.mkdirSync(path.dirname(outputPath), { recursive: true })
fs.writeFileSync(outputPath, `${JSON.stringify(manifest, null, 2)}\n`)
console.log(`persona manifest: ${selected.length} confirmed facts -> ${outputPath}`)
