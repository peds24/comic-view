// Per-card 3D positioning for the shelf carousel, as a pure function of a
// card's offset from the focused index — receding both left and right,
// matching the Waxlog reference (see docs/superpowers/specs/2026-09-02-3d-browsing-ui-design.md).

export interface CardTransform {
  translateX: number
  translateZ: number
  rotateY: number
  scale: number
  opacity: number
  blur: number
  zIndex: number
}

const STEP_X = 132
const STEP_Z = -70
const TILT_DEG = 34
const FOCUS_SCALE = 1.28
const MIN_SCALE = 0.62
const SCALE_FALLOFF = 0.14
const MIN_OPACITY = 0.18
const OPACITY_FALLOFF = 0.22
const MAX_BLUR = 3.5
const BLUR_STEP = 0.9
const FADE_OUT_BEYOND = 5

export function computeCardTransform(offset: number): CardTransform {
  const abs = Math.abs(offset)
  return {
    translateX: offset * STEP_X,
    translateZ: abs === 0 ? 0 : abs * STEP_Z,
    rotateY: offset === 0 ? 0 : offset > 0 ? -TILT_DEG : TILT_DEG,
    scale: offset === 0 ? FOCUS_SCALE : Math.max(MIN_SCALE, 1 - abs * SCALE_FALLOFF),
    opacity: abs > FADE_OUT_BEYOND ? 0 : Math.max(MIN_OPACITY, 1 - abs * OPACITY_FALLOFF),
    blur: offset === 0 ? 0 : Math.min(MAX_BLUR, abs * BLUR_STEP),
    zIndex: 100 - abs,
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
