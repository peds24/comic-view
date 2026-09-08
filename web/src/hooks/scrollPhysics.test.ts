import { describe, expect, it } from 'vitest'
import { snapToNearest, stepPhysics } from './scrollPhysics'

describe('stepPhysics', () => {
  it('advances position by velocity and decays velocity by friction', () => {
    const next = stepPhysics({ position: 0, velocity: 10 }, 0.9)
    expect(next.position).toBeCloseTo(10)
    expect(next.velocity).toBeCloseTo(9)
  })

  it('zeroes out velocity once it decays below the snap threshold', () => {
    const next = stepPhysics({ position: 0, velocity: 0.005 }, 0.9)
    expect(next.velocity).toBe(0)
  })

  it('applies friction repeatedly toward zero', () => {
    let state = { position: 0, velocity: 100 }
    for (let i = 0; i < 200; i++) state = stepPhysics(state, 0.9)
    expect(state.velocity).toBe(0)
  })
})

describe('snapToNearest', () => {
  it('rounds to the nearest integer index', () => {
    expect(snapToNearest(4.6, 100)).toBe(5)
    expect(snapToNearest(4.4, 100)).toBe(4)
  })

  it('clamps to the valid index range', () => {
    expect(snapToNearest(-3, 100)).toBe(0)
    expect(snapToNearest(500, 100)).toBe(99)
  })

  it('handles a single-item list', () => {
    expect(snapToNearest(5, 1)).toBe(0)
  })
})
