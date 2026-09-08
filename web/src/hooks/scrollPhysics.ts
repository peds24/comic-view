const SNAP_VELOCITY_THRESHOLD = 0.01

export interface PhysicsState {
  position: number
  velocity: number
}

export function stepPhysics(state: PhysicsState, friction: number): PhysicsState {
  const position = state.position + state.velocity
  const velocity = state.velocity * friction
  return {
    position,
    velocity: Math.abs(velocity) < SNAP_VELOCITY_THRESHOLD ? 0 : velocity,
  }
}

export function snapToNearest(position: number, itemCount: number): number {
  if (itemCount <= 0) return 0
  const rounded = Math.round(position)
  return Math.min(itemCount - 1, Math.max(0, rounded))
}
