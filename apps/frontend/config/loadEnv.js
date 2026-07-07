const fs = require('fs')
const path = require('path')

function normalizeValue(value) {
  if (!value) return ''
  const trimmed = value.trim()
  if (
    (trimmed.startsWith('"') && trimmed.endsWith('"')) ||
    (trimmed.startsWith("'") && trimmed.endsWith("'"))
  ) {
    return trimmed.slice(1, -1)
  }
  return trimmed
}

function loadEnvFromFile(filename) {
  const filepath = path.resolve(__dirname, '..', filename)
  if (!fs.existsSync(filepath)) {
    return
  }

  const content = fs.readFileSync(filepath, 'utf8')
  for (const line of content.split(/\r?\n/)) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) continue
    const separatorIndex = trimmed.indexOf('=')
    if (separatorIndex === -1) continue

    const key = trimmed.slice(0, separatorIndex).trim()
    const value = normalizeValue(trimmed.slice(separatorIndex + 1))
    if (key && process.env[key] === undefined) {
      process.env[key] = value
    }
  }
}

function loadFrontendEnv() {
  loadEnvFromFile('.env')
}

module.exports = { loadFrontendEnv }
