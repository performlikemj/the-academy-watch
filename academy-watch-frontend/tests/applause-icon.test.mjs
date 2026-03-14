import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import path from 'node:path'

const targetFiles = [
  'src/pages/WriteupPage.jsx',
  'src/components/CommentaryCard.jsx'
]

test('applaud buttons render a clapping icon (not thumbs up)', async () => {
  const contents = await Promise.all(
    targetFiles.map(async (relativePath) => {
      const absolutePath = path.resolve(process.cwd(), relativePath)
      return fs.readFile(absolutePath, 'utf8')
    })
  )

  contents.forEach((content, index) => {
    const filename = targetFiles[index]
    assert.equal(
      content.includes('ThumbsUp'),
      false,
      `${filename} should not reference the ThumbsUp icon for applause`
    )
    assert.equal(
      content.includes('ClapIcon'),
      true,
      `${filename} should render the shared ClapIcon for applause`
    )
  })
})
