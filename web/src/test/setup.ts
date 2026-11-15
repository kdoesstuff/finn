import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(() => {
  // Node-environment tests (build/) have no DOM to clean.
  if (typeof window === 'undefined') return
  cleanup()
  window.history.replaceState(null, '', '/')
})
