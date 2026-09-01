// @vitest-environment jsdom

import { afterEach, describe, expect, it } from 'vitest'
import { createApp, defineComponent, h, nextTick, resolveComponent } from 'vue'
import { registerElementPlusComponents } from '../element-plus.js'

function mountRadioApp() {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const app = createApp(
    defineComponent({
      data: () => ({ model: 'a' }),
      render() {
        return h(
          resolveComponent('el-radio-group'),
          {
            modelValue: this.model,
            'onUpdate:modelValue': (value) => {
              this.model = value
            },
          },
          () => [
            h(resolveComponent('el-radio-button'), { value: 'a' }, () => '甲'),
            h(resolveComponent('el-radio-button'), { value: 'b' }, () => '乙'),
          ]
        )
      },
    })
  )
  registerElementPlusComponents(app)
  const vm = app.mount(container)
  return { container, vm }
}

function mountCheckboxApp() {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const app = createApp(
    defineComponent({
      render() {
        return h(resolveComponent('el-checkbox'), { modelValue: true }, () => '选择')
      },
    })
  )
  registerElementPlusComponents(app)
  app.mount(container)
  return container
}

afterEach(() => {
  document.body.innerHTML = ''
})

describe('Element Plus component registration', () => {
  it('resolves el-radio-group / el-radio-button to real components', async () => {
    const { container } = mountRadioApp()
    await nextTick()
    expect(container.querySelector('.el-radio-group')).not.toBeNull()
    expect(container.querySelectorAll('.el-radio-button').length).toBe(2)
    expect(container.querySelector('.el-radio-button.is-active')).not.toBeNull()
  })

  it('updates the model when a radio button is clicked', async () => {
    const { container, vm } = mountRadioApp()
    await nextTick()
    const inputs = container.querySelectorAll('.el-radio-button__original-radio')
    expect(inputs.length).toBe(2)
    inputs[1].checked = true
    inputs[1].dispatchEvent(new Event('change', { bubbles: true }))
    await nextTick()
    expect(vm.model).toBe('b')
    expect(container.querySelectorAll('.el-radio-button')[1].classList.contains('is-active')).toBe(true)
  })

  it('resolves el-checkbox to the real component', async () => {
    const container = mountCheckboxApp()
    await nextTick()
    expect(container.querySelector('.el-checkbox')).not.toBeNull()
    expect(container.querySelector('.el-checkbox .el-checkbox__input')).not.toBeNull()
  })
})
