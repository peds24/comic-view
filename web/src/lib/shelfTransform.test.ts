import { describe, expect, it } from 'vitest'
import { computeCardTransform } from './shelfTransform'

describe('computeCardTransform', () => {
  it('centers the focused card with no rotation or tilt', () => {
    const t = computeCardTransform(0)
    expect(t.translateX).toBe(0)
    expect(t.translateZ).toBe(0)
    expect(t.rotateY).toBe(0)
    expect(t.scale).toBeGreaterThan(1)
    expect(t.opacity).toBe(1)
    expect(t.blur).toBe(0)
  })

  it('recedes to the right for a positive offset', () => {
    const t = computeCardTransform(2)
    expect(t.translateX).toBeGreaterThan(0)
    expect(t.translateZ).toBeLessThan(0)
    expect(t.rotateY).toBeLessThan(0)
  })

  it('recedes to the left for a negative offset, mirroring the positive case', () => {
    const right = computeCardTransform(2)
    const left = computeCardTransform(-2)
    expect(left.translateX).toBe(-right.translateX)
    expect(left.translateZ).toBe(right.translateZ)
    expect(left.rotateY).toBe(-right.rotateY)
    expect(left.scale).toBe(right.scale)
    expect(left.opacity).toBe(right.opacity)
  })

  it('shrinks and dims farther from the focus, never going negative', () => {
    const near = computeCardTransform(1)
    const far = computeCardTransform(4)
    expect(far.scale).toBeLessThan(near.scale)
    expect(far.opacity).toBeLessThan(near.opacity)
    expect(far.scale).toBeGreaterThan(0)
    expect(far.opacity).toBeGreaterThan(0)
  })

  it('fades fully out beyond the render window', () => {
    const t = computeCardTransform(6)
    expect(t.opacity).toBe(0)
  })

  it('gives the focused card the highest z-index', () => {
    expect(computeCardTransform(0).zIndex).toBeGreaterThan(computeCardTransform(1).zIndex)
    expect(computeCardTransform(1).zIndex).toBeGreaterThan(computeCardTransform(3).zIndex)
  })
})
