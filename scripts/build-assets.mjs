import { cp, mkdir, readdir } from 'node:fs/promises'
import { resolve, join } from 'node:path'

// Copy only application-owned public assets. Documents always pass through Django.
const root = resolve('static')
await mkdir(root, { recursive: true })
for (const entry of await readdir('public', { withFileTypes: true })) {
  if (entry.name === 'documents') continue
  await cp(join('public', entry.name), join(root, entry.name), {
    recursive: true,
    filter: (source) => !source.split(/[\\/]/).join('/').includes('/photos/source'),
  })
}
console.log('Public assets copied; PDF files remain behind publication checks.')
