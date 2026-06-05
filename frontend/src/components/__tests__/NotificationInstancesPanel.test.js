import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { parse as parseSfc } from '@vue/compiler-sfc'
import { baseParse } from '@vue/compiler-dom'

const __dirname = dirname(fileURLToPath(import.meta.url))
const panelSource = readFileSync(resolve(__dirname, '../NotificationInstancesPanel.vue'), 'utf8')
const panelTemplate = parseSfc(panelSource).descriptor.template.content
const panelAst = baseParse(panelTemplate)

function getPropText(prop) {
  if (prop.type === 6) return prop.value?.content || ''
  return [prop.name, prop.arg?.content, prop.exp?.content].filter(Boolean).join(' ')
}

function nodeContains(node, text) {
  const ownText = [
    node.content,
    ...(node.props || []).map(getPropText),
  ].filter(Boolean).join(' ')

  return ownText.includes(text) || (node.children || []).some((child) => nodeContains(child, text))
}

function collectFormGridBlocks(node, blocks = []) {
  if (node.type === 1) {
    const classProp = node.props.find((prop) => prop.type === 6 && prop.name === 'class')
    const classNames = classProp?.value?.content?.split(/\s+/) || []
    if (node.tag === 'div' && classNames.includes('notification-instance-form-grid')) {
      const conditional = node.props.find((prop) => prop.type === 7 && ['if', 'else-if', 'else'].includes(prop.name))
      blocks.push({
        conditionType: conditional?.name || '',
        condition: conditional?.exp?.content || '',
        node,
      })
    }
  }
  for (const child of node.children || []) {
    collectFormGridBlocks(child, blocks)
  }
  return blocks
}

describe('NotificationInstancesPanel template', () => {
  const getFormGridBlock = (condition) => {
    const block = collectFormGridBlocks(panelAst).find((item) => item.condition === condition)
    expect(block, `missing notification form block for ${condition}`).toBeDefined()
    return block
  }

  it('keeps socket settings out of webhook notification forms', () => {
    const webhookBlock = getFormGridBlock("form.type === 'webhook'")
    const socketBlock = getFormGridBlock("form.type === 'socket'")

    expect(webhookBlock.conditionType).toBe('else-if')
    expect(nodeContains(webhookBlock.node, 'settings.notificationWebhookPayload')).toBe(true)
    expect(nodeContains(webhookBlock.node, 'settings.notificationSocketProtocol')).toBe(false)
    expect(socketBlock.conditionType).toBe('else-if')
    expect(nodeContains(socketBlock.node, 'settings.notificationSocketProtocol')).toBe(true)
  })

  it('uses explicit type branches instead of a catch-all notification settings form', () => {
    const formGridBlocks = collectFormGridBlocks(panelAst)
    const typeSpecificConditions = formGridBlocks
      .map((block) => block.condition)
      .filter((condition) => condition.startsWith('form.type'))

    expect(typeSpecificConditions).toEqual([
      "form.type === 'email'",
      "form.type === 'webhook'",
      "form.type === 'email'",
      "form.type === 'socket'",
    ])
    expect(formGridBlocks).not.toContainEqual(expect.objectContaining({ conditionType: 'else' }))
  })
})
