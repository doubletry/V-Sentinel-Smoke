<template>
  <div
    class="roi-drawer-overlay"
    :class="{ 'read-only': readOnly }"
    @keydown="onKeyDown"
    @keyup="onKeyUp"
    tabindex="0"
    ref="overlayEl"
  >
    <canvas
      ref="canvasEl"
      class="roi-canvas"
      :class="{ 'is-panning': isPanning, 'space-down': spaceHeld && !readOnly }"
      @mousedown="onMouseDown"
      @mousemove="onMouseMove"
      @mouseup="onMouseUp"
      @mouseleave="onMouseLeave"
      @wheel.prevent="onWheel"
      @contextmenu.prevent
      @dblclick.prevent="onDblClick"
    />

    <!-- Floating context menu at mouse position when a shape is selected.
         选中形状时在鼠标位置显示的浮动上下文菜单。 -->
    <div
      v-if="!readOnly && !isDrawing && selectedIdx !== null"
      class="roi-context-menu"
      :style="contextMenuStyle"
    >
      <el-select
        v-model="shapes[selectedIdx].tag"
        size="small"
        class="tag-select"
        :placeholder="t('roi.selectTag')"
      >
        <el-option v-for="tag in tagOptions" :key="tag" :label="roiTagLabel(tag)" :value="tag" />
      </el-select>
      <el-button size="small" type="danger" @click="deleteSelected">
        <el-icon><Delete /></el-icon>
        {{ t('roi.deleteShape') }}
      </el-button>
    </div>

    <!-- Main toolbar — hidden while actively drawing to avoid blocking the
         canvas; shown again on cancel or completion.
         主工具栏——绘制时隐藏以免遮挡画布，取消或完成时重新显示。 -->
    <div v-if="!isDrawing" class="roi-toolbar">
      <!-- Zoom controls + mode badge (shown in both edit and preview modes).
           缩放控件 + 模式徽章（编辑模式和预览模式都显示）。 -->
      <el-tag size="small" type="warning" effect="dark" class="frozen-badge">
        {{ readOnly ? t('roi.liveZoomBadge') : t('roi.frozenBadge') }}
      </el-tag>
      <el-button-group class="zoom-group">
        <el-button size="small" :disabled="zoom <= MIN_ZOOM + 1e-6" @click="zoomOutBtn" :title="t('roi.zoomOut')">
          <el-icon><ZoomOut /></el-icon>
        </el-button>
        <el-button size="small" disabled class="zoom-level-btn">
          {{ t('roi.zoomLevel', { percent: Math.round(zoom * 100) }) }}
        </el-button>
        <el-button size="small" :disabled="zoom >= MAX_ZOOM - 1e-6" @click="zoomInBtn" :title="t('roi.zoomIn')">
          <el-icon><ZoomIn /></el-icon>
        </el-button>
        <el-button size="small" :disabled="Math.abs(zoom - 1) < 1e-6 && Math.abs(panX - identityPan.x) < 1e-6 && Math.abs(panY - identityPan.y) < 1e-6" @click="resetView" :title="t('roi.resetView')">
          <el-icon><Refresh /></el-icon>
        </el-button>
      </el-button-group>

      <template v-if="!readOnly">
        <el-button-group>
          <el-button
            size="small"
            :type="mode === 'polygon' ? 'primary' : 'default'"
            @click="mode = 'polygon'"
          >
            <el-icon><EditPen /></el-icon>
            {{ t('roi.polygon') }}
          </el-button>
          <el-button
            size="small"
            :type="mode === 'rectangle' ? 'primary' : 'default'"
            @click="mode = 'rectangle'"
          >
            <el-icon><Crop /></el-icon>
            {{ t('roi.rectangle') }}
          </el-button>
        </el-button-group>

        <el-tag type="info" effect="dark">
          {{ t('roi.boundScene') }}: {{ boundSceneLabel }}
        </el-tag>

        <el-button size="small" type="success" :loading="saving" @click="save">
          <el-icon><Check /></el-icon>
          {{ t('roi.saveRois') }}
        </el-button>
        <el-button size="small" @click="exportRois">
          <el-icon><Download /></el-icon>
          {{ t('roi.exportRois') }}
        </el-button>
        <el-button size="small" @click="triggerImport">
          <el-icon><Upload /></el-icon>
          {{ t('roi.importRois') }}
        </el-button>
        <input
          ref="importInputEl"
          type="file"
          accept=".yaml,.yml"
          style="display: none"
          @change="handleImportFile"
        />
        <el-button size="small" @click="emit('close')">
          <el-icon><Close /></el-icon>
          {{ t('roi.exitEdit') }}
        </el-button>
      </template>

      <template v-else>
        <el-tag type="info" effect="dark">{{ t('roi.previewMode') }}</el-tag>
        <el-button size="small" @click="emit('close')">
          <el-icon><Close /></el-icon>
          {{ t('roi.closePreview') }}
        </el-button>
      </template>
    </div>

    <!-- Finish-polygon button shown only during polygon drawing
         仅在多边形绘制过程中显示完成按钮 -->
    <div v-if="!readOnly && isDrawing && mode === 'polygon'" class="draw-finish-btn">
      <el-button
        size="small"
        type="primary"
        :disabled="currentPoints.length < 3"
        @click="finishPolygon"
      >
        <el-icon><Check /></el-icon>
        {{ t('roi.finishPolygon') }}
      </el-button>
    </div>

    <div v-if="!readOnly && isDrawing" class="draw-hint">
      {{ mode === 'polygon' ? t('roi.polygonHint') : t('roi.rectangleHint') }}
      <br />
      <span class="draw-hint-sub">{{ t('roi.panHint') }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import ElMessage from 'element-plus/es/components/message/index'
import { ZoomIn, ZoomOut, Refresh } from '@element-plus/icons-vue'
import { useSourceStore } from '../stores/source.js'
import { useAppSettingsStore } from '../stores/appSettings.js'
import { scenesApi, sourcesApi } from '../api/index.js'
import { localizedSceneLabel, sceneScopedRoiTagLabel } from '../utils/roiTags.js'
import {
  MIN_ZOOM,
  MAX_ZOOM,
  WHEEL_STEP,
  clampPan,
  identityView,
  screenToWorld,
  zoomAt,
} from '../utils/roiView.js'

const props = defineProps({
  source: {
    type: Object,
    required: true,
  },
  readOnly: {
    type: Boolean,
    default: false,
  },
})
const emit = defineEmits(['close'])

const store = useSourceStore()
const appSettingsStore = useAppSettingsStore()
const { t, locale } = useI18n()
const DEFAULT_SCENE_ID = 'smoke'

const canvasEl = ref(null)
const overlayEl = ref(null)
const importInputEl = ref(null)
const mode = ref('polygon')
const saving = ref(false)

const shapes = ref([])
const scenes = ref([])
const selectedIdx = ref(null)
const isDrawing = ref(false)
const currentPoints = ref([])
const rectStart = ref(null)
const pointerPos = ref(null)
/** Screen-relative position where the shape was selected (for floating menu).
    形状被选中时的屏幕相对坐标（用于浮动菜单）。 */
const selectionPos = ref({ x: 0, y: 0 })

// ── View transform (zoom + pan) state ──────────────────────────────────────
// View transform maps world-space (the same coordinate system as the
// existing getVideoRect / canvasToNorm helpers) to screen-space.
// Forward: screen = world * scale + pan ; Inverse: world = (screen - pan)/scale
const zoom = ref(1)
const panX = ref(0)
const panY = ref(0)
const spaceHeld = ref(false)
const isPanning = ref(false)
let panStart = null

// Frozen frame state — captured from the underlying <video> element in edit
// mode only. Preview mode keeps the live video running and applies the same
// CSS transform as the canvas so zoom/pan remains aligned.
const frameCanvas = ref(null) // HTMLCanvasElement | null
const cssFallbackZoom = ref(false) // true if drawImage threw SecurityError
let videoElRef = null
let shouldResumeVideo = false
let rafHandle = 0
let pendingMetadataVideoEl = null
let pendingMetadataHandler = null

const sceneById = computed(() => new Map(scenes.value.map((scene) => [scene.id, scene])))
const activePluginId = computed(() => appSettingsStore.activePluginId || DEFAULT_SCENE_ID)
const boundScene = computed(() =>
  sceneById.value.get(activePluginId.value)
  || sceneById.value.get(DEFAULT_SCENE_ID)
)
const tagOptions = computed(() => boundScene.value?.default_roi_tags || [])
const boundSceneLabel = computed(() =>
  localizedSceneLabel(boundScene.value, locale.value) || props.source?.scene_id || DEFAULT_SCENE_ID
)

function roiTagLabel(tag) {
  return sceneScopedRoiTagLabel(boundScene.value, tag, locale.value)
}

/** Compute inline style positioning the context menu near the mouse click.
    计算内联样式，将上下文菜单定位在鼠标点击附近。
    Clamps to overlay bounds so the menu stays fully visible.
    限制在 overlay 边界内以确保菜单完全可见。 */
const contextMenuStyle = computed(() => {
  const overlay = overlayEl.value
  if (!overlay) return {}
  const rect = overlay.getBoundingClientRect()
  // Convert screen-relative click coordinates to overlay-relative
  let left = selectionPos.value.x - rect.left
  let top = selectionPos.value.y - rect.top

  // Estimate menu dimensions for boundary clamping
  const menuW = 260 // approximate rendered width
  const menuH = 48  // approximate rendered height

  // The CSS transform is translate(-50%, -140%), so the effective origin is:
  //   effectiveLeft = left - menuW/2
  //   effectiveTop  = top  - menuH*1.4
  const effLeft = left - menuW / 2
  const effTop = top - menuH * 1.4

  // If the menu would overflow left / right / top, shift it
  if (effLeft < 4) left = menuW / 2 + 4
  if (effLeft + menuW > rect.width - 4) left = rect.width - menuW / 2 - 4
  if (effTop < 4) {
    // Place below the click instead — override transform in style
    return {
      left: `${left}px`,
      top: `${top}px`,
      transform: 'translate(-50%, 20px)',
    }
  }

  return {
    left: `${left}px`,
    top: `${top}px`,
  }
})

let dragState = null

function clampPanReactive(scaleVal = zoom.value) {
  const canvas = canvasEl.value
  if (!canvas) return
  const videoRect = getVideoRect()
  const clamped = clampPan(panX.value, panY.value, scaleVal, videoRect, {
    width: canvas.width,
    height: canvas.height,
  })
  panX.value = clamped.panX
  panY.value = clamped.panY
}

const identityPan = computed(() => {
  const canvas = canvasEl.value
  if (!canvas) return { x: 0, y: 0 }
  const videoRect = getVideoRect()
  const id = identityView(videoRect, { width: canvas.width, height: canvas.height })
  return { x: id.panX, y: id.panY }
})

function resetView() {
  zoom.value = 1
  panX.value = 0
  panY.value = 0
  clampPanReactive(1)
  scheduleRender()
}

function applyZoomAt(cursor, newScale) {
  const canvas = canvasEl.value
  if (!canvas) return
  const videoRect = getVideoRect()
  const next = zoomAt(
    cursor,
    newScale,
    { scale: zoom.value, panX: panX.value, panY: panY.value },
    videoRect,
    { width: canvas.width, height: canvas.height },
  )
  zoom.value = next.scale
  panX.value = next.panX
  panY.value = next.panY
  scheduleRender()
}

function zoomInBtn() {
  const canvas = canvasEl.value
  if (!canvas) return
  applyZoomAt({ x: canvas.width / 2, y: canvas.height / 2 }, zoom.value * WHEEL_STEP)
}

function zoomOutBtn() {
  const canvas = canvasEl.value
  if (!canvas) return
  applyZoomAt({ x: canvas.width / 2, y: canvas.height / 2 }, zoom.value / WHEEL_STEP)
}

function scheduleRender() {
  if (rafHandle) return
  rafHandle = requestAnimationFrame(() => {
    rafHandle = 0
    render()
  })
}

function resizeCanvas() {
  if (!canvasEl.value) return
  const parent = canvasEl.value.parentElement
  canvasEl.value.width = parent.clientWidth
  canvasEl.value.height = parent.clientHeight
  clampPanReactive()
  render()
}

function getCanvasPos(event) {
  const rect = canvasEl.value.getBoundingClientRect()
  return { x: event.clientX - rect.left, y: event.clientY - rect.top }
}

/** Convert a mouse event to world-space coordinates (the coordinate system
    used by getVideoRect / canvasToNorm). */
function getWorldPos(event) {
  return screenToWorld(getCanvasPos(event), {
    scale: zoom.value,
    panX: panX.value,
    panY: panY.value,
  })
}

function getVideoElement() {
  const overlayRoot = overlayEl.value || canvasEl.value?.parentElement || null
  if (!overlayRoot) return null

  // RoiDrawer is a sibling of VideoPlayer inside the same grid cell, not its parent.
  const gridCell = overlayRoot.closest('.grid-cell') || overlayRoot.parentElement
  return gridCell?.querySelector('video.video-element') || null
}

function getVideoRect() {
  const canvas = canvasEl.value
  if (!canvas) {
    return { x: 0, y: 0, width: 1, height: 1 }
  }

  const cw = canvas.width || 1
  const ch = canvas.height || 1
  const videoEl = getVideoElement()

  if (!videoEl || !videoEl.videoWidth || !videoEl.videoHeight) {
    return { x: 0, y: 0, width: cw, height: ch }
  }

  const containerAspect = cw / ch
  const videoAspect = videoEl.videoWidth / videoEl.videoHeight

  if (containerAspect > videoAspect) {
    const height = ch
    const width = height * videoAspect
    return {
      x: (cw - width) / 2,
      y: 0,
      width,
      height,
    }
  }

  const width = cw
  const height = width / videoAspect
  return {
    x: 0,
    y: (ch - height) / 2,
    width,
    height,
  }
}

function clampNorm(point) {
  return {
    x: Math.max(0, Math.min(1, point.x)),
    y: Math.max(0, Math.min(1, point.y)),
  }
}

function canvasToNorm(point, videoRect = getVideoRect()) {
  const width = videoRect.width || 1
  const height = videoRect.height || 1
  return clampNorm({
    x: (point.x - videoRect.x) / width,
    y: (point.y - videoRect.y) / height,
  })
}

function normToCanvas(point, videoRect = getVideoRect()) {
  return {
    x: videoRect.x + point.x * videoRect.width,
    y: videoRect.y + point.y * videoRect.height,
  }
}

function isInsideVideo(point, videoRect = getVideoRect()) {
  return (
    point.x >= videoRect.x &&
    point.x <= videoRect.x + videoRect.width &&
    point.y >= videoRect.y &&
    point.y <= videoRect.y + videoRect.height
  )
}

function isPointInPolygon(point, polygon) {
  let inside = false
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const xi = polygon[i].x
    const yi = polygon[i].y
    const xj = polygon[j].x
    const yj = polygon[j].y

    const intersect =
      yi > point.y !== yj > point.y &&
      point.x < ((xj - xi) * (point.y - yi)) / (yj - yi) + xi

    if (intersect) inside = !inside
  }
  return inside
}

function hitTestShapes(pos) {
  const videoRect = getVideoRect()
  // Hit radius is fixed in screen pixels (8 px); divide by zoom for world space.
  const hitRadius = 8 / Math.max(zoom.value, 1e-6)
  for (let i = shapes.value.length - 1; i >= 0; i--) {
    const shape = shapes.value[i]
    const canvasPoints = shape.points.map((point) => normToCanvas(point, videoRect))

    for (let j = 0; j < canvasPoints.length; j++) {
      const dx = canvasPoints[j].x - pos.x
      const dy = canvasPoints[j].y - pos.y
      if (Math.sqrt(dx * dx + dy * dy) < hitRadius) {
        return { shapeIdx: i, vertexIdx: j }
      }
    }

    if (canvasPoints.length >= 3 && isPointInPolygon(pos, canvasPoints)) {
      return { shapeIdx: i, vertexIdx: 'body' }
    }
  }

  return null
}

function drawShape(ctx, shape, idx, videoRect, invZoom) {
  const points = shape.points.map((point) => normToCanvas(point, videoRect))
  if (!points.length) return

  const selected = idx === selectedIdx.value && !props.readOnly
  const color = selected ? '#f0c040' : '#40a0f0'

  ctx.beginPath()
  ctx.moveTo(points[0].x, points[0].y)
  for (let i = 1; i < points.length; i++) {
    ctx.lineTo(points[i].x, points[i].y)
  }
  ctx.closePath()
  ctx.strokeStyle = color
  ctx.lineWidth = 2 * invZoom
  ctx.stroke()
  ctx.fillStyle = `${color}22`
  ctx.fill()

  if (!props.readOnly) {
    points.forEach((point) => {
      ctx.beginPath()
      ctx.arc(point.x, point.y, 4.5 * invZoom, 0, Math.PI * 2)
      ctx.fillStyle = color
      ctx.fill()
    })
  }

  if (shape.tag) {
    ctx.font = `${12 * invZoom}px sans-serif`
    ctx.fillStyle = color
    ctx.fillText(shape.tag, points[0].x + 6 * invZoom, points[0].y - 8 * invZoom)
  }
}

function drawPolygonPreview(ctx, videoRect, invZoom) {
  if (!(isDrawing.value && mode.value === 'polygon' && currentPoints.value.length)) return

  const points = currentPoints.value.map((point) => normToCanvas(point, videoRect))
  const pointer = pointerPos.value
    ? normToCanvas(canvasToNorm(pointerPos.value, videoRect), videoRect)
    : null

  ctx.beginPath()
  ctx.moveTo(points[0].x, points[0].y)
  for (let i = 1; i < points.length; i++) {
    ctx.lineTo(points[i].x, points[i].y)
  }
  if (pointer) {
    ctx.lineTo(pointer.x, pointer.y)
  }
  ctx.strokeStyle = '#80ff80'
  ctx.lineWidth = 2 * invZoom
  ctx.stroke()

  if (pointer && points.length >= 2) {
    ctx.beginPath()
    ctx.setLineDash([4 * invZoom, 4 * invZoom])
    ctx.moveTo(pointer.x, pointer.y)
    ctx.lineTo(points[0].x, points[0].y)
    ctx.strokeStyle = '#80ff80aa'
    ctx.stroke()
    ctx.setLineDash([])
  }

  points.forEach((point) => {
    ctx.beginPath()
    ctx.arc(point.x, point.y, 4 * invZoom, 0, Math.PI * 2)
    ctx.fillStyle = '#80ff80'
    ctx.fill()
  })
}

function drawRectanglePreview(ctx, videoRect, invZoom) {
  if (!(isDrawing.value && mode.value === 'rectangle' && rectStart.value && pointerPos.value)) return

  const start = normToCanvas(rectStart.value, videoRect)
  const end = normToCanvas(canvasToNorm(pointerPos.value, videoRect), videoRect)
  const x = Math.min(start.x, end.x)
  const y = Math.min(start.y, end.y)
  const width = Math.abs(start.x - end.x)
  const height = Math.abs(start.y - end.y)

  ctx.strokeStyle = '#80ff80'
  ctx.lineWidth = 2 * invZoom
  ctx.strokeRect(x, y, width, height)
}

function render() {
  const canvas = canvasEl.value
  if (!canvas) return

  const ctx = canvas.getContext('2d')
  const videoRect = getVideoRect()
  ctx.clearRect(0, 0, canvas.width, canvas.height)

  // Apply view transform: screen = world * scale + pan
  ctx.save()
  ctx.translate(panX.value, panY.value)
  ctx.scale(zoom.value, zoom.value)

  const invZoom = 1 / Math.max(zoom.value, 1e-6)

  // Edit mode draws the frozen frame inside the videoRect. Preview mode (or
  // edit-mode tainted-canvas fallback) keeps the underlying <video> visible
  // behind the canvas and scaled via CSS, so we skip drawing a frame here.
  if (frameCanvas.value && !cssFallbackZoom.value) {
    try {
      ctx.drawImage(
        frameCanvas.value,
        videoRect.x,
        videoRect.y,
        videoRect.width,
        videoRect.height,
      )
    } catch (_err) {
      // Defensive: should never happen because frameCanvas is our own canvas.
    }
  }

  // Dashed outline of the video region.
  ctx.save()
  ctx.setLineDash([6 * invZoom, 4 * invZoom])
  ctx.strokeStyle = 'rgba(64, 160, 240, 0.5)'
  ctx.lineWidth = 1 * invZoom
  ctx.strokeRect(videoRect.x, videoRect.y, videoRect.width, videoRect.height)
  ctx.restore()

  shapes.value.forEach((shape, idx) => drawShape(ctx, shape, idx, videoRect, invZoom))
  drawPolygonPreview(ctx, videoRect, invZoom)
  drawRectanglePreview(ctx, videoRect, invZoom)

  ctx.restore()
}

function clearDrawingState() {
  isDrawing.value = false
  currentPoints.value = []
  rectStart.value = null
  dragState = null
}

function createShapeWithDefaultTag(type, points) {
  const defaultTag = tagOptions.value[0] || ''
  shapes.value.push({ type, points, tag: defaultTag })
  selectedIdx.value = shapes.value.length - 1
}

function finalizeRectangle(startNorm, endNorm) {
  const x1 = Math.min(startNorm.x, endNorm.x)
  const y1 = Math.min(startNorm.y, endNorm.y)
  const x2 = Math.max(startNorm.x, endNorm.x)
  const y2 = Math.max(startNorm.y, endNorm.y)

  if (x2 - x1 <= 0.01 || y2 - y1 <= 0.01) return

  createShapeWithDefaultTag('rectangle', [
    { x: x1, y: y1 },
    { x: x2, y: y1 },
    { x: x2, y: y2 },
    { x: x1, y: y2 },
  ])
}

function finishPolygon() {
  if (!(mode.value === 'polygon' && isDrawing.value && currentPoints.value.length >= 3)) {
    return
  }

  createShapeWithDefaultTag('polygon', currentPoints.value.map((point) => ({ ...point })))
  clearDrawingState()
  render()
}

function onMouseDown(event) {
  overlayEl.value?.focus()

  // Pan: middle button OR Space+left button. Allowed in both readOnly and edit modes.
  const isPanGesture =
    event.button === 1 || (event.button === 0 && spaceHeld.value)
  if (isPanGesture) {
    isPanning.value = true
    panStart = {
      mouseX: event.clientX,
      mouseY: event.clientY,
      panX: panX.value,
      panY: panY.value,
    }
    event.preventDefault()
    return
  }

  if (event.button !== 0) return
  if (props.readOnly) return

  const videoEl = getVideoElement()
  if (!videoEl) {
    ElMessage.warning(t('roi.videoNotReady'))
    return
  }

  const pos = getWorldPos(event)
  pointerPos.value = pos
  const videoRect = getVideoRect()

  if (!isDrawing.value) {
    const hit = hitTestShapes(pos)
    if (hit) {
      selectedIdx.value = hit.shapeIdx
      selectionPos.value = { x: event.clientX, y: event.clientY }
      dragState = {
        shapeIdx: hit.shapeIdx,
        vertexIdx: hit.vertexIdx,
        startMouse: pos,
        startPoints: shapes.value[hit.shapeIdx].points.map((point) => ({ ...point })),
      }
      scheduleRender()
      return
    }
  }

  if (!isInsideVideo(pos, videoRect)) {
    ElMessage.warning(t('roi.pointOutside'))
    return
  }

  const pointNorm = canvasToNorm(pos, videoRect)
  selectedIdx.value = null

  if (mode.value === 'polygon') {
    isDrawing.value = true
    currentPoints.value.push(pointNorm)
    scheduleRender()
    return
  }

  if (mode.value === 'rectangle') {
    if (!isDrawing.value || !rectStart.value) {
      isDrawing.value = true
      rectStart.value = pointNorm
    } else {
      finalizeRectangle(rectStart.value, pointNorm)
      clearDrawingState()
    }
    scheduleRender()
  }
}

function onMouseMove(event) {
  if (isPanning.value && panStart) {
    panX.value = panStart.panX + (event.clientX - panStart.mouseX)
    panY.value = panStart.panY + (event.clientY - panStart.mouseY)
    clampPanReactive()
    scheduleRender()
    return
  }

  const pos = getWorldPos(event)
  pointerPos.value = pos

  if (props.readOnly) {
    scheduleRender()
    return
  }

  if (dragState) {
    const videoRect = getVideoRect()
    const width = videoRect.width || 1
    const height = videoRect.height || 1
    // pos and startMouse are both in world space → delta is already correct.
    const dx = (pos.x - dragState.startMouse.x) / width
    const dy = (pos.y - dragState.startMouse.y) / height
    const shape = shapes.value[dragState.shapeIdx]

    if (dragState.vertexIdx === 'body') {
      shape.points = dragState.startPoints.map((point) =>
        clampNorm({ x: point.x + dx, y: point.y + dy })
      )
    } else {
      shape.points = dragState.startPoints.map((point, index) => {
        if (index === dragState.vertexIdx) {
          return clampNorm({ x: point.x + dx, y: point.y + dy })
        }
        return { ...point }
      })
    }

    scheduleRender()
    return
  }

  if (isDrawing.value) {
    scheduleRender()
  }
}

function onMouseUp(event) {
  if (isPanning.value) {
    isPanning.value = false
    panStart = null
    return
  }
  if (dragState) {
    // Update context-menu anchor to the release position so the floating
    // toolbar follows the shape after dragging.
    // 更新上下文菜单锚点到释放位置，使浮动工具栏跟随形状拖拽。
    selectionPos.value = { x: event.clientX, y: event.clientY }
    dragState = null
    scheduleRender()
  }
}

function onMouseLeave() {
  // Cancel any in-progress pan if the cursor leaves the canvas; otherwise
  // a stuck pan-state can prevent normal interaction.
  if (isPanning.value) {
    isPanning.value = false
    panStart = null
  }
}

function onWheel(event) {
  // Zoom centered on the cursor; clamp into [MIN_ZOOM, MAX_ZOOM].
  const cursor = getCanvasPos(event)
  const factor = event.deltaY < 0 ? WHEEL_STEP : 1 / WHEEL_STEP
  applyZoomAt(cursor, zoom.value * factor)
}

function onDblClick() {
  if (!props.readOnly && mode.value === 'polygon') {
    finishPolygon()
  }
}

function onKeyDown(event) {
  if (event.code === 'Space' || event.key === ' ') {
    if (!spaceHeld.value) spaceHeld.value = true
    // Prevent page scroll when overlay is focused.
    event.preventDefault()
    return
  }

  if (event.key === 'Escape') {
    if (isDrawing.value) {
      clearDrawingState()
      render()
    } else {
      emit('close')
    }
    return
  }

  if (props.readOnly) return

  if (event.key === 'Enter' && mode.value === 'polygon') {
    finishPolygon()
    return
  }

  if ((event.key === 'Delete' || event.key === 'Backspace') && selectedIdx.value !== null) {
    deleteSelected()
  }
}

function onKeyUp(event) {
  if (event.code === 'Space' || event.key === ' ') {
    spaceHeld.value = false
    // If pan ended with Space release, drop pan state.
    if (isPanning.value) {
      isPanning.value = false
      panStart = null
    }
  }
}

function deleteSelected() {
  if (props.readOnly) return
  if (selectedIdx.value === null) return

  shapes.value.splice(selectedIdx.value, 1)
  selectedIdx.value = null
  render()
}

async function save() {
  if (props.readOnly) {
    emit('close')
    return
  }

  if (!tagOptions.value.length) {
    ElMessage.warning(t('roi.noSceneTagOptions'))
    return
  }

  const invalidIndex = shapes.value.findIndex(
    (shape) => !shape.tag || !tagOptions.value.includes(shape.tag)
  )

  if (invalidIndex !== -1) {
    selectedIdx.value = invalidIndex
    ElMessage.warning(t('roi.tagRequired'))
    render()
    return
  }

  saving.value = true
  try {
    const rois = shapes.value.map((shape) => ({
      type: shape.type,
      points: shape.points,
      tag: shape.tag,
    }))

    await store.updateSource(props.source.id, { rois })
    ElMessage.success(t('roi.roisSaved'))
  } catch (err) {
    ElMessage.error(err.message || t('roi.saveFailed'))
  } finally {
    saving.value = false
  }
}

// ── ROI Export / Import ───────────────────────────────────────────────────

async function exportRois() {
  try {
    const data = await sourcesApi.exportRois(props.source.id)
    const blob = data instanceof Blob ? data : new Blob([data], { type: 'application/x-yaml' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${props.source.name || 'rois'}_rois.yaml`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    ElMessage.success(t('roi.exportSuccess'))
  } catch (err) {
    ElMessage.error(err.message || t('roi.exportFailed'))
  }
}

function triggerImport() {
  importInputEl.value?.click()
}

async function handleImportFile(event) {
  const file = event.target.files?.[0]
  if (!file) return
  try {
    const result = await sourcesApi.importRois(props.source.id, file)
    // Reload shapes from the result returned by the server
    const rois = result?.rois || []
    shapes.value = rois.map((roi) => ({
      type: roi.type,
      points: (roi.points || []).map((point) => clampNorm({ x: point.x, y: point.y })),
      tag: roi.tag || '',
    }))
    selectedIdx.value = null
    clearDrawingState()
    render()
    // Refresh the store to keep data consistent
    await store.fetchSources()
    ElMessage.success(t('roi.importSuccess'))
  } catch (err) {
    ElMessage.error(err.message || t('roi.importFailed'))
  } finally {
    // Reset file input so the same file can be imported again
    if (importInputEl.value) importInputEl.value.value = ''
  }
}

function loadExistingRois() {
  const source = store.sources.find((item) => item.id === props.source.id)
  const rois = source?.rois || props.source.rois || []
  shapes.value = rois.map((roi) => ({
    type: roi.type,
    points: roi.points.map((point) => clampNorm({ x: point.x, y: point.y })),
    tag: roi.tag || '',
  }))
  selectedIdx.value = null
  clearDrawingState()
  render()
}

const resizeObserver = new ResizeObserver(resizeCanvas)

// ── Frame-freeze / snapshot helpers ────────────────────────────────────────

/** Snapshot the current frame of the underlying <video> into an offscreen
 *  canvas. On SecurityError (tainted canvas) fall back to CSS-zoom mode.
 *  对底层 <video> 当前帧进行快照；若画布被污染则降级使用 CSS 缩放。 */
function captureFrame(videoEl) {
  if (!videoEl || !videoEl.videoWidth || !videoEl.videoHeight) {
    frameCanvas.value = null
    return false
  }
  try {
    const off = document.createElement('canvas')
    off.width = videoEl.videoWidth
    off.height = videoEl.videoHeight
    const ctx = off.getContext('2d')
    ctx.drawImage(videoEl, 0, 0, off.width, off.height)
    // Touch the pixels so a CORS taint surfaces synchronously here, not
    // later inside render(). If this throws we drop to CSS-zoom fallback.
    ctx.getImageData(0, 0, 1, 1)
    frameCanvas.value = off
    cssFallbackZoom.value = false
    return true
  } catch (err) {
    // SecurityError → cross-origin/tainted canvas → CSS-zoom fallback.
    frameCanvas.value = null
    cssFallbackZoom.value = true
    ElMessage.warning(t('roi.frameCaptureFailed'))
    return false
  }
}

/** Edit mode only: pause the video, hide it if snapshot succeeds, or keep it
 *  visible and scaled via CSS in fallback mode. */
function freezeVideo() {
  videoElRef = getVideoElement()
  if (!videoElRef) return
  shouldResumeVideo = !videoElRef.paused
  try {
    videoElRef.pause()
  } catch (_err) {
    // ignore
  }
  captureFrame(videoElRef)
  applyVideoStyle()
}

function applyVideoStyle() {
  if (!videoElRef) return
  if (props.readOnly || cssFallbackZoom.value) {
    // In preview mode, or in edit-mode CSS-zoom fallback, keep the <video>
    // visible and apply a CSS transform that mirrors the canvas view
    // transform. Preview mode deliberately does not pause or snapshot video.
    videoElRef.style.transformOrigin = '0 0'
    videoElRef.style.transform = `translate(${panX.value}px, ${panY.value}px) scale(${zoom.value})`
    videoElRef.style.visibility = 'visible'
  } else if (frameCanvas.value) {
    // Snapshot succeeded → hide the live video, the canvas paints the frame.
    videoElRef.style.transform = ''
    videoElRef.style.transformOrigin = ''
    videoElRef.style.visibility = 'hidden'
  }
}

function restoreVideo() {
  clearPendingMetadataListener()
  if (!videoElRef) return
  videoElRef.style.visibility = ''
  videoElRef.style.transform = ''
  videoElRef.style.transformOrigin = ''
  if (shouldResumeVideo) {
    videoElRef.play().catch(() => {
      // play() may reject if the element is mid-reconnect; ignore.
    })
  }
  shouldResumeVideo = false
  videoElRef = null
  frameCanvas.value = null
  cssFallbackZoom.value = false
}

function enableLiveVideoZoom() {
  videoElRef = getVideoElement()
  if (!videoElRef) return
  // Preview mode never pauses the video, so exiting preview must not force
  // playback if the element was already paused by something else.
  shouldResumeVideo = false
  frameCanvas.value = null
  cssFallbackZoom.value = false
  applyVideoStyle()
}

function clearPendingMetadataListener() {
  if (pendingMetadataVideoEl && pendingMetadataHandler) {
    pendingMetadataVideoEl.removeEventListener('loadeddata', pendingMetadataHandler)
    pendingMetadataVideoEl.removeEventListener('loadedmetadata', pendingMetadataHandler)
  }
  pendingMetadataVideoEl = null
  pendingMetadataHandler = null
}

function registerPendingMetadataListener(videoEl, onReady) {
  clearPendingMetadataListener()
  const handler = () => {
    clearPendingMetadataListener()
    onReady()
  }
  pendingMetadataVideoEl = videoEl
  pendingMetadataHandler = handler
  videoEl.addEventListener('loadeddata', handler, { once: true })
  videoEl.addEventListener('loadedmetadata', handler, { once: true })
}

function reSnapshotIfPossible() {
  if (props.readOnly) {
    enableLiveVideoZoom()
    resetView()
    return
  }

  const videoEl = getVideoElement()
  if (!videoEl) return
  // Only re-capture if videoWidth is available; otherwise wait until next
  // loadedmetadata.
  if (videoEl.videoWidth && videoEl.videoHeight) {
    videoElRef = videoEl
    try { videoEl.pause() } catch (_e) { /* ignore */ }
    captureFrame(videoEl)
    applyVideoStyle()
    resetView()
  } else {
    registerPendingMetadataListener(videoEl, () => {
      if (props.readOnly) return
      freezeVideo()
      resetView()
    })
  }
}

// Keep CSS transform in sync with reactive zoom/pan in fallback mode.
watch([zoom, panX, panY], () => {
  if (props.readOnly || cssFallbackZoom.value) applyVideoStyle()
})

watch(() => props.source?.id, () => {
  loadExistingRois()
  resetView()
  reSnapshotIfPossible()
})
watch(activePluginId, () => {
  selectedIdx.value = null
  clearDrawingState()
  resetView()
  reSnapshotIfPossible()
})

watch(() => props.readOnly, () => {
  selectedIdx.value = null
  clearDrawingState()
  // Clear the previous mode's CSS/snapshot state before attaching the video
  // again for the next mode below.
  restoreVideo()
  resetView()
  if (props.readOnly) {
    enableLiveVideoZoom()
  } else {
    reSnapshotIfPossible()
  }
  render()
})

onMounted(async () => {
  if (!appSettingsStore.loaded) {
    await appSettingsStore.fetchSettings().catch(() => {
      // Keep fallback defaults when settings API is unavailable.
    })
  }
  scenes.value = await scenesApi.list().catch(() => [])

  loadExistingRois()
  resizeCanvas()
  overlayEl.value?.focus()

  // Edit mode freezes the underlying video as soon as the drawer mounts.
  // Preview mode keeps the video live and only applies zoom/pan transforms.
  const videoEl = getVideoElement()
  if (videoEl) {
    if (props.readOnly) {
      enableLiveVideoZoom()
      render()
    } else if (videoEl.videoWidth && videoEl.videoHeight) {
      freezeVideo()
      render()
    } else {
      registerPendingMetadataListener(videoEl, () => {
        if (props.readOnly) return
        freezeVideo()
        render()
      })
    }
  }

  if (canvasEl.value) {
    resizeObserver.observe(canvasEl.value.parentElement)
  }
})

onBeforeUnmount(() => {
  resizeObserver.disconnect()
  if (rafHandle) {
    cancelAnimationFrame(rafHandle)
    rafHandle = 0
  }
  restoreVideo()
})
</script>

<style scoped>
.roi-drawer-overlay {
  position: absolute;
  inset: 0;
  z-index: 100;
  outline: none;
}

.roi-canvas {
  position: absolute;
  inset: 0;
  cursor: crosshair;
}

.roi-canvas.space-down {
  cursor: grab;
}

.roi-canvas.is-panning {
  cursor: grabbing;
}

.roi-drawer-overlay.read-only .roi-canvas {
  cursor: grab;
}

.roi-drawer-overlay.read-only .roi-canvas.is-panning {
  cursor: grabbing;
}

.roi-context-menu {
  position: absolute;
  display: flex;
  align-items: center;
  gap: 6px;
  z-index: 120;
  background: rgba(0, 0, 0, 0.78);
  padding: 6px;
  border-radius: 8px;
  transform: translate(-50%, -140%);
  pointer-events: auto;
  white-space: nowrap;
}

.roi-toolbar {
  position: absolute;
  right: 8px;
  bottom: 8px;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: nowrap;
  gap: 6px;
  z-index: 110;
  background: rgba(0, 0, 0, 0.62);
  padding: 6px;
  border-radius: 8px;
}

.roi-toolbar :deep(.el-button span) {
  white-space: nowrap;
}

.frozen-badge {
  font-weight: 600;
}

.zoom-group .zoom-level-btn {
  min-width: 64px;
  font-variant-numeric: tabular-nums;
  pointer-events: none;
  opacity: 0.85;
}

.tag-select {
  min-width: 140px;
}

.draw-finish-btn {
  position: absolute;
  right: 8px;
  bottom: 8px;
  z-index: 110;
  background: rgba(0, 0, 0, 0.62);
  padding: 6px;
  border-radius: 8px;
}

.draw-hint {
  position: absolute;
  left: 8px;
  bottom: 8px;
  z-index: 110;
  background: rgba(0, 0, 0, 0.68);
  color: #d4deef;
  font-size: 12px;
  line-height: 1.4;
  padding: 6px 8px;
  border-radius: 6px;
  max-width: min(80%, 360px);
}

.draw-hint-sub {
  opacity: 0.78;
}
</style>
