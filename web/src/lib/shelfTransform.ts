// Per-card 3D positioning for the shelf carousel, as a pure function of a
// card's offset from the focused index — receding both left and right,
// matching the Waxlog reference (see docs/superpowers/specs/2026-09-02-3d-browsing-ui-design.md).
//
// `offset` is a real number, not just an integer: while the shelf is in
// motion (a scroll/arrow-key fling in flight), the caller passes each
// card's offset from the physics engine's continuous fractional position,
// not just the settled integer index — that's what makes the shelf visibly
// glide instead of sitting frozen until the fling settles and jumping once.
// rotateY/scale are therefore blended smoothly over the |offset| 0..1
// range rather than switching in one step at offset === 0, so nothing
// pops as a card crosses the focus point mid-glide.

export interface CardTransform {
  translateX: number
  translateZ: number
  rotateY: number
  scale: number
  opacity: number
  blur: number
  zIndex: number
}

const STEP_X = 190
const STEP_Z = -90
const TILT_DEG = 34
const FOCUS_SCALE = 1.28
const MIN_SCALE = 0.62
const SCALE_FALLOFF = 0.14
const MIN_OPACITY = 0.18
const OPACITY_FALLOFF = 0.22
const MAX_BLUR = 3.5
const BLUR_STEP = 0.9
const FADE_OUT_BEYOND = 5

function falloffScale(abs: number): number {
  return Math.max(MIN_SCALE, 1 - abs * SCALE_FALLOFF)
}

export function computeCardTransform(offset: number): CardTransform {
  const abs = Math.abs(offset)
  const sign = Math.sign(offset)
  const settle = Math.min(1, abs) // 0 at the focus, 1 by the time a card is a full slot away

  return {
    translateX: offset * STEP_X,
    translateZ: abs === 0 ? 0 : abs * STEP_Z,
    rotateY: offset === 0 ? 0 : -sign * settle * TILT_DEG,
    scale: FOCUS_SCALE - (FOCUS_SCALE - falloffScale(abs)) * settle,
    opacity: abs > FADE_OUT_BEYOND ? 0 : Math.max(MIN_OPACITY, 1 - abs * OPACITY_FALLOFF),
    blur: Math.min(MAX_BLUR, abs * BLUR_STEP),
    zIndex: Math.round(100 - abs),
  }
}

export function cardTransformStyle(offset: number): Record<string, string> {
  const t = computeCardTransform(offset)
  return {
    '--tx': `${t.translateX}px`,
    '--tz': `${t.translateZ}px`,
    '--ry': `${t.rotateY}deg`,
    '--sc': String(t.scale),
    '--op': String(t.opacity),
    '--bl': `${t.blur}px`,
    '--z': String(t.zIndex),
  }
}
