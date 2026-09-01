import { createApp } from 'vue'
import {
  Bell,
  Check,
  ChatRound,
  CircleClose,
  Close,
  Crop,
  Delete,
  Document,
  Download,
  Edit,
  EditPen,
  House,
  Monitor,
  Plus,
  Setting,
  Upload,
  User,
  VideoCamera,
  View,
} from '@element-plus/icons-vue'
import 'element-plus/dist/index.css'
import './styles/element-dark.css'

import App from './App.vue'
import { i18n } from './i18n/index.js'
import router from './router/index.js'
import pinia from './stores/pinia.js'
import config from './config.js'
import { registerElementPlusComponents } from './element-plus.js'

const app = createApp(App)

registerElementPlusComponents(app)

// Register only the icons used by the current UI to avoid pulling the full icon set.
const elementPlusIcons = [
  ['Bell', Bell],
  ['Check', Check],
  ['ChatRound', ChatRound],
  ['CircleClose', CircleClose],
  ['Close', Close],
  ['Crop', Crop],
  ['Delete', Delete],
  ['Document', Document],
  ['Download', Download],
  ['Edit', Edit],
  ['EditPen', EditPen],
  ['House', House],
  ['Monitor', Monitor],
  ['Plus', Plus],
  ['Setting', Setting],
  ['Upload', Upload],
  ['User', User],
  ['VideoCamera', VideoCamera],
  ['View', View],
]

elementPlusIcons.forEach(([name, component]) => {
  app.component(name, component)
})

app.use(pinia)
app.use(router)
app.use(i18n)

// Make config available globally
app.config.globalProperties.$config = config

// Set document title
document.title = config.siteName

app.mount('#app')
