# web

The Longbox — the browsing shelf (sub-project A) and the owner-only quick-add
form at `/admin` (sub-project B), for the comic/manga library in the parent
`comic-view-ui` repo. React + TypeScript + Vite; independent toolchain from
the Python package.

## Develop

Run the Python backend (serves `data/library.json` and covers, and the
`/api/*` quick-add routes) alongside the Vite dev server:

```bash
# from the repo root
comic-library serve --port 8000

# from web/
npm run dev
```

`vite.config.ts` proxies `/data` and `/api` to `127.0.0.1:8000`.

## Test & build

```bash
npm run test
npm run build
```
