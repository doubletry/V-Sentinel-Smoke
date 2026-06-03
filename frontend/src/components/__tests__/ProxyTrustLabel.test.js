import { describe, expect, it } from 'vitest'
import ProxyTrustLabel from '../ProxyTrustLabel.js'

describe('ProxyTrustLabel', () => {
  it('renders the label text and puts the hint on the tooltip trigger', () => {
    const render = ProxyTrustLabel.setup({
      label: '信任反向代理头',
      hint: '启用后，审计日志和登录封禁会优先使用 nginx 传入的 X-Forwarded-For / X-Real-IP。',
    })
    const vnode = render()

    const tooltipNode = vnode.children[0]
    expect(tooltipNode.props.content).toBe('启用后，审计日志和登录封禁会优先使用 nginx 传入的 X-Forwarded-For / X-Real-IP。')
    expect(tooltipNode.props.placement).toBe('top')
    expect(tooltipNode.children.default().children).toBe('信任反向代理头')

    expect(vnode.children[1].type.name).toBe('ElIcon')
  })
})
