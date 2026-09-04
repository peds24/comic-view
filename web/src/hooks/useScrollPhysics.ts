import { useCallback, useEffect, useRef, useState } from 'react'
import { snapToNearest, stepPhysics, type PhysicsState } from './scrollPhysics'

const FRICTION = 0.92
const WHEEL_TO_VELOCITY = 0.05

export function useScrollPhysics(itemCount: number, onIndexChange: (index: number) => void) {
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

  const handleWheel = useCallback(
    (deltaY: number) => {
      stateRef.current = { ...stateRef.current, velocity: stateRef.current.velocity + deltaY * WHEEL_TO_VELOCITY }
      if (rafRef.current === null) rafRef.current = requestAnimationFrame(tick)
    },
    [tick],
  )

  useEffect(() => {
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
    }
  }, [])

  return { position, handleWheel }
}
