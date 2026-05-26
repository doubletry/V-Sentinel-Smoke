import { describe, it, expect } from 'vitest'
import {
  clampZoom,
  screenToWorld,
  worldToScreen,
  clampPan,
  zoomAt,
  identityView,
  MIN_ZOOM,
  MAX_ZOOM,
} from '../roiView.js'

const SOURCE = { x: 40, y: 20, width: 400, height: 300 }
const VIEWPORT = { width: 480, height: 360 }

describe('clampZoom', () => {
  it('clamps to [MIN_ZOOM, MAX_ZOOM]', () => {
    expect(clampZoom(0.1)).toBe(MIN_ZOOM)
    expect(clampZoom(100)).toBe(MAX_ZOOM)
    expect(clampZoom(2.5)).toBe(2.5)
  })

  it('falls back to MIN_ZOOM on non-finite input', () => {
    expect(clampZoom(NaN)).toBe(MIN_ZOOM)
    expect(clampZoom(Infinity)).toBe(MIN_ZOOM)
    expect(clampZoom(-Infinity)).toBe(MIN_ZOOM)
  })
})

describe('screenToWorld / worldToScreen', () => {
  it('round-trips for arbitrary view', () => {
    const view = { scale: 3.4, panX: -120, panY: 55 }
    const world = { x: 87.3, y: 142.1 }
    const screen = worldToScreen(world, view)
    const back = screenToWorld(screen, view)
    expect(back.x).toBeCloseTo(world.x, 9)
    expect(back.y).toBeCloseTo(world.y, 9)
  })

  it('identity view leaves points unchanged', () => {
    const view = { scale: 1, panX: 0, panY: 0 }
    const p = { x: 12, y: 34 }
    expect(worldToScreen(p, view)).toEqual(p)
    expect(screenToWorld(p, view)).toEqual(p)
  })
})

describe('clampPan', () => {
  it('centers the source when scaled size <= viewport on an axis', () => {
    const { panX, panY } = clampPan(999, -999, 1, SOURCE, VIEWPORT)
    expect(SOURCE.x * 1 + panX).toBeCloseTo((VIEWPORT.width - SOURCE.width) / 2)
    expect(SOURCE.y * 1 + panY).toBeCloseTo((VIEWPORT.height - SOURCE.height) / 2)
  })

  it('clamps pan so the source covers the viewport when zoomed in', () => {
    const scale = 3
    const { panX, panY } = clampPan(10000, 10000, scale, SOURCE, VIEWPORT)
    expect(SOURCE.x * scale + panX).toBeLessThanOrEqual(1e-9)
    expect((SOURCE.x + SOURCE.width) * scale + panX).toBeGreaterThanOrEqual(VIEWPORT.width - 1e-9)
    expect(SOURCE.y * scale + panY).toBeLessThanOrEqual(1e-9)
    expect((SOURCE.y + SOURCE.height) * scale + panY).toBeGreaterThanOrEqual(VIEWPORT.height - 1e-9)
  })

  it('clamps the opposite direction too', () => {
    const scale = 3
    const { panX, panY } = clampPan(-10000, -10000, scale, SOURCE, VIEWPORT)
    expect(SOURCE.x * scale + panX).toBeLessThanOrEqual(1e-9)
    expect((SOURCE.x + SOURCE.width) * scale + panX).toBeGreaterThanOrEqual(VIEWPORT.width - 1e-9)
    expect(SOURCE.y * scale + panY).toBeLessThanOrEqual(1e-9)
    expect((SOURCE.y + SOURCE.height) * scale + panY).toBeGreaterThanOrEqual(VIEWPORT.height - 1e-9)
  })
})

describe('zoomAt', () => {
  it('keeps the world point under the cursor anchored across zoom changes', () => {
    const cursor = { x: 250, y: 180 }
    const view = identityView(SOURCE, VIEWPORT)
    const worldBefore = screenToWorld(cursor, view)
    const newView = zoomAt(cursor, 4, view, SOURCE, VIEWPORT)
    const worldAfter = screenToWorld(cursor, newView)
    expect(newView.scale).toBe(4)
    expect(worldAfter.x).toBeCloseTo(worldBefore.x, 6)
    expect(worldAfter.y).toBeCloseTo(worldBefore.y, 6)
  })

  it('clamps scale to [MIN_ZOOM, MAX_ZOOM]', () => {
    const cursor = { x: 100, y: 100 }
    const view = identityView(SOURCE, VIEWPORT)
    expect(zoomAt(cursor, 100, view, SOURCE, VIEWPORT).scale).toBe(MAX_ZOOM)
    expect(zoomAt(cursor, 0.01, view, SOURCE, VIEWPORT).scale).toBe(MIN_ZOOM)
  })

  it('reset to scale=1 yields identityView regardless of intermediate pan', () => {
    const cursor = { x: 300, y: 200 }
    const v0 = identityView(SOURCE, VIEWPORT)
    const v1 = zoomAt(cursor, 3, v0, SOURCE, VIEWPORT)
    const v2 = zoomAt(cursor, 1, v1, SOURCE, VIEWPORT)
    expect(v2.scale).toBe(1)
    expect(v2.panX).toBeCloseTo(v0.panX, 6)
    expect(v2.panY).toBeCloseTo(v0.panY, 6)
  })
})

describe('coordinate consistency', () => {
  it('round-trips world->screen->world across zoom levels', () => {
    const samples = [
      { scale: 1, panX: 0, panY: 0 },
      { scale: 2.5, panX: -120, panY: 30 },
      { scale: 8, panX: -1500, panY: -800 },
    ]
    const points = [
      { x: 100, y: 50 },
      { x: 300, y: 200 },
      { x: 440, y: 320 },
    ]
    for (const view of samples) {
      for (const p of points) {
        const s = worldToScreen(p, view)
        const w = screenToWorld(s, view)
        expect(w.x).toBeCloseTo(p.x, 9)
        expect(w.y).toBeCloseTo(p.y, 9)
      }
    }
  })
})
