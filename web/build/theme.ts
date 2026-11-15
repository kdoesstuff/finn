// Colours the browser needs before CSS loads (the web app manifest and theme-color). They mirror
// --paper in src/styles/tokens.css; a test keeps the two in step, so a restyle stays a token change.
export const paper = {
  light: '#ECEFE8',
  dark: '#121722',
} as const
