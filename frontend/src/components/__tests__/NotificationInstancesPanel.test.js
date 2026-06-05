import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const panelSource = readFileSync(resolve(__dirname, '../NotificationInstancesPanel.vue'), 'utf8')

describe('NotificationInstancesPanel template', () => {
  it('keeps socket settings out of webhook notification forms', () => {
    const socketFormBlock = panelSource.match(
      /<div v-else-if="form\.type === 'socket'" class="notification-instance-form-grid">[\s\S]*?notificationSocketMessageHex[\s\S]*?<\/div>\s*<\/div>\s*<\/el-form>/,
    )

    expect(panelSource).toContain('<div v-else-if="form.type === \'webhook\'" class="notification-instance-form-grid">')
    expect(socketFormBlock).not.toBeNull()
    expect(panelSource).not.toContain('<div v-else class="notification-instance-form-grid">')
  })
})
