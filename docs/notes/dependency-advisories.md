# Web dependency advisories (15 Nov 2026)

GitHub flagged three advisories on `main` after the B5/B6 push. All three come from build and lint
tooling in `web/`; none is in what the browser downloads.

| Advisory | Severity | Path into the tree | Patched release | Done |
| --- | --- | --- | --- | --- |
| [GHSA-3g3m-2fjr-6pw4](https://github.com/advisories/GHSA-3g3m-2fjr-6pw4) `glob` >=9.0.0 <=14.0.1 (AbortSignal cancellation bypass) | moderate | `vite-plugin-pwa` 2.0.0 > `workbox-build` 7.4.1 > `glob` 11.1.0 | 14.0.2 | Override, scoped to `workbox-build`: `glob` 14.0.6 |
| [GHSA-g3hv-75wg-m249](https://github.com/advisories/GHSA-g3hv-75wg-m249) `minimatch` >=7.0.0 <11.0.1 (globparts amplification) | moderate | `typescript-eslint` 8.72.2 > `@typescript-eslint/typescript-estree` > `minimatch` 10.2.6; also `glob` 11.1.0 > `minimatch` 10.2.6 | 11.0.1 | Override, scoped to `typescript-estree`: `minimatch` 11.0.8 (the version ESLint already uses); `glob` 14.0.6 brings 11.0.8 itself |
| [GHSA-gcqx-w48m-w2h4](https://github.com/advisories/GHSA-gcqx-w48m-w2h4) `deepmerge` >=4.2.0 <=4.3.1 (prototype poisoning in `mergeObject()`) | low | `workbox-build` > `@rollup/plugin-node-resolve` 16.0.3 > `deepmerge` 4.3.1 | **none**: 4.3.1 is the latest release | Not changed; risk accepted, reasons below |

## Why overrides, and why these versions

No newer release of the direct dependencies exists to upgrade to (checked with `npm view`):
`typescript-eslint` 8.72.2, `vite-plugin-pwa` 2.0.0, `workbox-build` 7.4.1 and
`@rollup/plugin-node-resolve` 16.0.3 are all the latest. So the patched packages are forced with
`overrides` in `web/package.json`, each scoped to the one dependent that pulls the vulnerable copy,
and pinned exactly, as everything else in the project is:

- `glob` 14.0.6 for `workbox-build` (which asks for `^11.0.1`). Its only use is one call in
  `workbox-build/build/lib/get-file-details.js`: `globSync(globPattern, { cwd, follow, ignore })`.
  `globSync` and those three options exist unchanged in 14.0.6 (checked by `require`). Engines:
  node `18 || 20 || >=22`.
- `minimatch` 11.0.8 for `@typescript-eslint/typescript-estree` (which asks for `^10.2.2`). Its only
  use is `minimatch(filePath, pattern, { dot: true })` in `useProgramFromProjectService.js`; the
  named export is unchanged in 11 (checked by `require`). Engines: node `20 || >=22`. ESLint 10
  already runs on this exact version in the same tree.
- Not overridden globally: `filelist` (under `jake`/`ejs`) uses `minimatch` 5.1.9, outside the
  advisory's range, with the v5 API that 11 does not offer.

The lockfile changes are exactly: `glob` 11.1.0 to 14.0.6, `path-scurry` 2.0.2 to 3.0.0, the two
nested `minimatch` 10.2.6 copies removed (both now dedupe to 11.0.8), and five packages only glob
11 needed (`@isaacs/cliui`, `foreground-child`, `jackspeak`, `package-json-from-dist`,
`signal-exit`) gone. The stale nested `minimatch` entry under `typescript-estree` had to be
removed from the lockfile by hand once: `npm install` otherwise keeps a locked version that no
longer satisfies the override (`npm ls` reported it "invalid").

## Why `deepmerge` stays

There is no patched release: 4.3.1 is the latest, and the advisory itself lists the patched
version as unknown. npm's only "fix" is `vite-plugin-pwa` 0.2.1, a years-old breaking downgrade.
Downgrading `deepmerge` below 4.2.0 would satisfy the scanner's range but bring back code from
before the earlier prototype-pollution guard, so it would not be safer.

It is not exploitable here: the advisory needs attacker-supplied source objects. Its one use in
`@rollup/plugin-node-resolve` is `deepMerge({}, defaults)`, on the plugin's own constant defaults,
at build time on our machines and CI; no input reaches it, and `deepmerge` is not in the built app
(`grep -rl "isMergeableObject\|deepmerge" dist` finds nothing). CI's audit blocks at high; this is
low. On GitHub, the Dependabot alert can be dismissed by the repository owner with "Risk is
tolerable to this project", linking here; it should be revisited when `deepmerge` or
`@rollup/plugin-node-resolve` ships a fix.

## Evidence (run in `web/`, Node 22.23.4, `CI=true`, `VITE_API_URL=https://finn-api-53vw.onrender.com`, `VITE_NETWORK_ENABLED=false`)

| Check | Result |
| --- | --- |
| `npm ci` from the new lockfile | installs cleanly; `npm ls` shows `glob@14.0.6`, `minimatch@11.0.8` everywhere in range, `deepmerge@4.3.1` |
| `npm audit` | before: 12 (2 low, 10 moderate); after: 4 low, 0 moderate, 0 high (one advisory, `deepmerge`, counted once per package on its path) |
| `npm audit --audit-level=high` | exit 0 |
| `npm run typecheck`, `npm run lint` | pass |
| `npm test` | 79 of 79 pass (5 files), including the lint-rule test under `CI=true` |
| `npm run build` | passes; service worker precaches 13 entries (370.00 KiB), the precached URL list identical to the build before the change, and the same set of files in `dist` |
| Playwright, both projects, system Chrome under the CI config | 27 passed, 3 skipped (by design: they need the deployed site) |

Not verified here: Node 26.13.1 (CI's version; the overridden packages' engines allow it), and the
run on GitHub's runners, which happens on push.
