// @vitest-environment jsdom

import { afterEach, describe, expect, it } from 'vitest'
import { createApp, nextTick } from 'vue'
import ProxyTrustLabel from '../ProxyTrustLabel.js'

afterEach(() => {
  document.body.innerHTML = ''
})

describe('ProxyTrustLabel', () => {
  it('renders the label as the tooltip trigger and keeps the hint on hover', async () => {
    const container = document.createElement('div')
    document.body.appendChild(container)

    createApp(ProxyTrustLabel, {
      label: '信任反向代理头',
      hint: '启用后，审计日志和登录封禁会优先使用 nginx 传入的 X-Forwarded-For / X-Real-IP。',
    }).mount(container)

    await nextTick()

    const trigger = container.querySelector('.settings-tooltip-label__trigger')
    expect(trigger).not.toBeNull()
    expect(trigger.textContent).toBe('信任反向代理头')
    expect(trigger.getAttribute('aria-label')).toBe(
      '信任反向代理头: 启用后，审计日志和登录封禁会优先使用 nginx 传入的 X-Forwarded-For / X-Real-IP。',
    )
    expect(trigger.querySelector('.settings-tooltip-label__icon')).not.toBeNull()

    trigger.dispatchEvent(new window.MouseEvent('mouseenter', { bubbles: true }))
    await nextTick()
    await new Promise((resolve) => setTimeout(resolve, 50))

    expect(document.body.textContent).toContain(
      '启用后，审计日志和登录封禁会优先使用 nginx 传入的 X-Forwarded-For / X-Real-IP。',
    )
  })
})
