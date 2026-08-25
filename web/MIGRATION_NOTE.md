# V1 web migration note

Source evidence: fixed repository commit `1ffb4cdd45c798556390c20e53fc2d265cd56471`.

The new workspace rewrites the selected visual behavior into new package boundaries:

- `web/src/app-shell.css` visual tokens became `packages/ui/src/styles/tokens.css`.
- Responsive sidebar, collapse, mobile drawer, focus, and reduced-motion behavior became `packages/ui/src/shell.tsx` and `packages/ui/src/styles/shell.css`.
- Loading, error, surface, status, and empty-state semantics became `packages/ui/src/primitives.tsx` and `packages/ui/src/styles/primitives.css`.

No source file was copied verbatim. Product-domain pages, API clients, proxies, browser identity, old selectors, and bundled runtime output were intentionally excluded. Desktop and Community consume only the new shared UI package and typed contracts.

Validation for this slice is executable through the root `web/` scripts: strict typecheck, Vitest/React Testing Library, and separate production builds for both applications.

TODO for the next Studio slice: connect the reserved React Query client, Zustand transient canvas state, and graph editor dependency to real versioned contracts; this slice intentionally adds no mock integrations.
