import { readdir } from 'node:fs/promises'
import { spawnSync } from 'node:child_process'
import { join } from 'node:path'

async function check(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name)
    if (entry.isDirectory()) await check(path)
    else if (/\.(m?js)$/.test(path)) {
      const result = spawnSync(process.execPath, ['--check', path], { stdio: 'inherit' })
      if (result.status) process.exitCode = result.status
    }
  }
}
for (const directory of ['frontend', 'scripts', 'tests/browser']) await check(directory)
