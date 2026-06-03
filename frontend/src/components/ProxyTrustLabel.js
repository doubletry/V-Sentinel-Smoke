import { defineComponent, h } from 'vue'
import ElIcon from 'element-plus/es/components/icon/index'
import ElTooltip from 'element-plus/es/components/tooltip/index'
import { QuestionFilled } from '@element-plus/icons-vue'

export default defineComponent({
  name: 'ProxyTrustLabel',
  props: {
    label: {
      type: String,
      required: true,
    },
    hint: {
      type: String,
      required: true,
    },
  },
  setup(props) {
    return () => h('span', { class: 'settings-tooltip-label' }, [
      h(ElTooltip, { content: props.hint, placement: 'top' }, {
        default: () => h('span', {
          class: 'settings-tooltip-label__trigger',
          'aria-label': `${props.label}: ${props.hint}`,
        }, props.label),
      }),
      h(ElIcon, { class: 'settings-tooltip-label__icon', 'aria-hidden': 'true' }, {
        default: () => h(QuestionFilled),
      }),
    ])
  },
})
