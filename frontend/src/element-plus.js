import ElAvatar from 'element-plus/es/components/avatar/index'
import ElBadge from 'element-plus/es/components/badge/index'
import ElButton, { ElButtonGroup } from 'element-plus/es/components/button/index'
import ElCheckbox from 'element-plus/es/components/checkbox/index'
import ElCol from 'element-plus/es/components/col/index'
import ElConfigProvider from 'element-plus/es/components/config-provider/index'
import ElContainer, { ElHeader, ElMain } from 'element-plus/es/components/container/index'
import ElDatePicker from 'element-plus/es/components/date-picker/index'
import ElDialog from 'element-plus/es/components/dialog/index'
import ElDivider from 'element-plus/es/components/divider/index'
import ElEmpty from 'element-plus/es/components/empty/index'
import ElForm, { ElFormItem } from 'element-plus/es/components/form/index'
import ElIcon from 'element-plus/es/components/icon/index'
import ElInput from 'element-plus/es/components/input/index'
import ElInputNumber from 'element-plus/es/components/input-number/index'
import ElLoading from 'element-plus/es/components/loading/index'
import ElMenu, { ElMenuItem } from 'element-plus/es/components/menu/index'
import ElPagination from 'element-plus/es/components/pagination/index'
import ElPopover from 'element-plus/es/components/popover/index'
import { ElRadioButton, ElRadioGroup } from 'element-plus/es/components/radio/index'
import ElRow from 'element-plus/es/components/row/index'
import ElScrollbar from 'element-plus/es/components/scrollbar/index'
import ElSelect, { ElOption } from 'element-plus/es/components/select/index'
import ElSkeleton from 'element-plus/es/components/skeleton/index'
import ElSpace from 'element-plus/es/components/space/index'
import ElSwitch from 'element-plus/es/components/switch/index'
import ElTabs, { ElTabPane } from 'element-plus/es/components/tabs/index'
import ElTable, { ElTableColumn } from 'element-plus/es/components/table/index'
import ElTag from 'element-plus/es/components/tag/index'
import ElTooltip from 'element-plus/es/components/tooltip/index'
import ElUpload from 'element-plus/es/components/upload/index'

// Register only the Element Plus components used by the current UI.
const elementPlusComponents = [
  ElAvatar,
  ElBadge,
  ElButton,
  ElButtonGroup,
  ElCheckbox,
  ElCol,
  ElConfigProvider,
  ElContainer,
  ElDatePicker,
  ElDialog,
  ElDivider,
  ElEmpty,
  ElForm,
  ElFormItem,
  ElHeader,
  ElIcon,
  ElInput,
  ElInputNumber,
  ElMain,
  ElMenu,
  ElMenuItem,
  ElOption,
  ElPagination,
  ElPopover,
  ElRadioButton,
  ElRadioGroup,
  ElRow,
  ElScrollbar,
  ElSelect,
  ElSkeleton,
  ElSpace,
  ElSwitch,
  ElTabs,
  ElTabPane,
  ElTable,
  ElTableColumn,
  ElTag,
  ElTooltip,
  ElUpload,
]

export function registerElementPlusComponents(app) {
  elementPlusComponents.forEach((component) => {
    app.component(component.name, component)
  })
  app.use(ElLoading)
}
