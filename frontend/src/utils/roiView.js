/**
 * Pure helpers for the RoiDrawer view transform (zoom + pan).
 * 用于 RoiDrawer 视图变换（缩放 + 平移）的纯函数辅助方法。
 *
 * The "world" coordinate space here is the on-screen canvas coordinate
 * system before any view transform is applied — i.e. the same space used
 * by the existing getVideoRect / canvasToNorm / normToCanvas helpers.
 * Screen coordinates are the actual mouse coordinates relative to the
 * canvas element.
 *
 * The forward transform is:
 *   screen = world * scale + pan
 * The inverse transform is:
 *   world  = (screen - pan) / scale
 *
 * These helpers are framework-agnostic and DOM-free so that they can be
 * unit tested without a browser.
 */

export const MIN_ZOOM = 1
export const MAX_ZOOM = 8
export const WHEEL_STEP = 1.2

export function clampZoom(zoom, min = MIN_ZOOM, max = MAX_ZOOM) {
  if (!Number.isFinite(zoom)) return min
  return Math.max(min, Math.min(max, zoom))
}

export function screenToWorld(point, view) {
  const scale = view.scale || 1
  return {
    x: (point.x - (view.panX || 0)) / scale,
    y: (point.y - (view.panY || 0)) / scale,
  }
}

export function worldToScreen(point, view) {
  const scale = view.scale || 1
  return {
    x: point.x * scale + (view.panX || 0),
    y: point.y * scale + (view.panY || 0),
  }
}

/**
 * Clamp pan so that the visible rectangle (viewport) is always covered by
 * the source rectangle after transformation. When the source, scaled by
 * `scale`, is smaller than the viewport on an axis it is centered on that
 * axis instead.
 *
 * 限制 pan，使变换后的源矩形始终覆盖视口；当某个方向上缩放后的源比视口小时，
 * 将其在该方向居中。
 *
 * source: the rectangle in world coordinates that should always be visible
 *         (e.g. the videoRect — only this region matters for ROI drawing).
 * viewport: the canvas size in screen coordinates (width/height).
 */
export function clampPan(panX, panY, scale, source, viewport) {
  const sx = source.x || 0
  const sy = source.y || 0
  const sw = source.width || 0
  const sh = source.height || 0
  const vw = viewport.width || 0
  const vh = viewport.height || 0

  const scaledW = sw * scale
  const scaledH = sh * scale

  let outX
  if (scaledW <= vw) {
    // Center the source horizontally inside the viewport.
    outX = (vw - scaledW) / 2 - sx * scale
  } else {
    // pan must keep [sx*scale + pan, sx*scale + pan + scaledW] covering [0, vw]
    const minPan = vw - (sx + sw) * scale
    const maxPan = -sx * scale
    outX = Math.max(minPan, Math.min(maxPan, panX))
  }

  let outY
  if (scaledH <= vh) {
    outY = (vh - scaledH) / 2 - sy * scale
  } else {
    const minPan = vh - (sy + sh) * scale
    const maxPan = -sy * scale
    outY = Math.max(minPan, Math.min(maxPan, panY))
  }

  return { panX: outX, panY: outY }
}

/**
 * Compute a new view (scale + pan) that zooms to `newScale` while keeping
 * the world point currently under `cursor` (in screen coords) anchored at
 * the same screen position. The returned pan is then clamped against
 * `source` and `viewport`.
 *
 * 在保持鼠标下世界坐标点屏幕位置不变的前提下缩放到 newScale；返回值已对 pan 做约束。
 */
export function zoomAt(cursor, newScale, view, source, viewport) {
  const clampedScale = clampZoom(newScale)
  // World point under cursor before zoom.
  const world = screenToWorld(cursor, view)
  // We want: cursor = world * clampedScale + newPan  =>  newPan = cursor - world * clampedScale
  const panX = cursor.x - world.x * clampedScale
  const panY = cursor.y - world.y * clampedScale
  const clamped = clampPan(panX, panY, clampedScale, source, viewport)
  return { scale: clampedScale, panX: clamped.panX, panY: clamped.panY }
}

/**
 * Returns the default identity view, with pan clamped so the source rect
 * is centered/covered inside the viewport at scale = 1.
 */
export function identityView(source, viewport) {
  const clamped = clampPan(0, 0, 1, source, viewport)
  return { scale: 1, panX: clamped.panX, panY: clamped.panY }
}
