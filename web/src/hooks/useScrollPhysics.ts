import { useCallback, useEffect, useRef, useState } from 'react'
import { snapToNearest, stepPhysics, type PhysicsState } from './scrollPhysics'

const FRICTION = 0.92
const WHEEL_TO_VELOCITY = 0.05
const ARROW_KEY_IMPULSE = 0.05
// Bounds how fast the shelf can ever move, regardless of input source.
// Without this, a sustained stream of impulses (a real trackpad swipe, or
// a held arrow key firing OS auto-repeat) arrives faster than one frame's
// friction decay can dissipate it, so each new impulse lands on top of
// velocity that's barely decayed — velocity (and therefore speed) keeps
// climbing for as long as the input continues, rocketing across the whole
// shelf in well under a second instead of coasting at a controllable pace.
const MAX_VELOCITY = 0.6

export function useScrollPhysics(itemCount: number, currentIndex: number, onIndexChange: (index: number) => void) {
  const [position, setPosition] = useState(0)
  const stateRef = useRef<PhysicsState>({ position: 0, velocity: 0 })
  const rafRef = useRef<number | null>(null)

  const tick = useCallback(() => {
    stateRef.current = stepPhysics(stateRef.current, FRICTION)
    setPosition(stateRef.current.position)

    if (stateRef.current.velocity === 0) {
      const snapped = snapToNearest(stateRef.current.position, itemCount)
      stateRef.current = { position: snapped, velocity: 0 }
      setPosition(snapped)
      onIndexChange(snapped)
      rafRef.current = null
      return
    }
    rafRef.current = requestAnimationFrame(tick)
  }, [itemCount, onIndexChange])

  // Shared by every input source (wheel, horizontal scroll, held arrow
  // keys) — repeated impulses stack onto the same decaying velocity, which
  // is the acceleration: keep scrolling/holding and each new impulse lands
  // on top of motion that hasn't decayed away yet.
  const applyImpulse = useCallback(
    (delta: number) => {
      const nextVelocity = stateRef.current.velocity + delta
      const clamped = Math.max(-MAX_VELOCITY, Math.min(MAX_VELOCITY, nextVelocity))
      stateRef.current = { ...stateRef.current, velocity: clamped }
      if (rafRef.current === null) rafRef.current = requestAnimationFrame(tick)
    },
    [tick],
  )

  const handleWheel = useCallback(
    (deltaX: number, deltaY: number) => applyImpulse((deltaX + deltaY) * WHEEL_TO_VELOCITY),
    [applyImpulse],
  )

  // A single, non-repeated key press steps precisely to the neighboring
  // item — matches the "precise alternative" the arrow keys are for. Once
  // the OS starts auto-repeating a held key (or a fling is already in
  // flight), presses feed the same velocity system as scrolling instead,
  // so holding the key accelerates exactly like a continuous scroll.
  const handleArrowKey = useCallback(
    (direction: 1 | -1, isRepeat: boolean) => {
      if (isRepeat || rafRef.current !== null) {
        applyImpulse(direction * ARROW_KEY_IMPULSE)
      } else {
        onIndexChange(Math.min(itemCount - 1, Math.max(0, currentIndex + direction)))
      }
    },
    [itemCount, currentIndex, onIndexChange, applyImpulse],
  )

  useEffect(() => {
    if (rafRef.current === null) {
      stateRef.current = { position: currentIndex, velocity: 0 }
      setPosition(currentIndex)
    }
  }, [currentIndex])

  useEffect(() => {
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
    }
  }, [])

  return { position, handleWheel, handleArrowKey }
}
