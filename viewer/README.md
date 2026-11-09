# NVIDIA SASS ISA Viewer

Static Vue viewer for the instruction databases and research notes in the
repository root.

## Development

```bash
cd viewer
npm install
npm run dev
```

`predev` rebuilds the browser catalog from `sm*.json` and `notes/` before Vite
starts.  Generated files live under `public/data/` and are not committed.

## Production build

```bash
cd viewer
npm run build
```

The output is a self-contained static site in `dist/`.  The router uses hash
URLs, so it works on GitHub Pages and other static hosts without a rewrite
proxy.

## Data pipeline

```bash
python3 tools/build_viewer_data.py
python3 tools/build_viewer_data.py --check
```

The generated layout is:

- `manifest.json`: architecture and instruction summaries
- `details/<arch>/<mnemonic>.json`: lazy-loaded encodings and note content

Raw `sm*.json` databases are never served to the browser.
