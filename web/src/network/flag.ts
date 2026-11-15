/**
 * True only in the full edition's build. Vite writes the value in at build time, so in the core
 * build every branch guarded by this constant is dead code and the bundler drops the network
 * components with it (`build.spec.ts` checks that the core bundle names none of them).
 */
export const NETWORK_BUILD: boolean = import.meta.env.VITE_NETWORK_ENABLED === 'true'
