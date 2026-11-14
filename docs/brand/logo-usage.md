# Karriere Pipeline — Brand Identity & Logo Usage Guide

## 1. Brand Concept: Forward Pipeline

The **Karriere Pipeline** brand mark represents **structured forward progression**: multiple job discovery conduits (LinkedIn, BA, specialized tech boards) converging seamlessly through automated intelligence into a single, high-conviction application stream.

```
       ┌───────────┐
──●───►│ Ingestion │───┐
       └───────────┘   │   ┌──────────────┐
                       ├──►│ Applications │──►
       ┌───────────┐   │   └──────────────┘
──●───►│ Ingestion │───┘
       └───────────┘
```

---

## 2. Canonical Brand Assets

All production vector and raster assets are managed in the repository:

| File Path | Description | Dimensions / Type |
|---|---|---|
| `frontend/src/assets/brand/logo-mark.svg` | Primary standalone vector mark | 24×24 viewBox, scalable vector |
| `frontend/src/assets/brand/logo-wordmark.svg` | Horizontal lockup (Mark + "Karriere Pipeline") | 190×32 viewBox, Inter typography |
| `frontend/public/favicon.svg` | Modern scalable SVG favicon | 32×32 viewBox, squircle container |
| `frontend/public/favicon-32x32.png` | Standard desktop browser tab favicon | 32×32 PNG |
| `frontend/public/favicon-16x16.png` | Compact address bar / bookmark icon | 16×16 PNG |
| `frontend/public/favicon.ico` | Multi-resolution legacy ICO container | Bundled 16×16 & 32×32 ICO |
| `frontend/public/apple-touch-icon.png` | iOS Home Screen / Safari Touch Icon | 180×180 PNG |
| `frontend/public/icon-192.png` | Android Chrome PWA Icon | 192×192 PNG |
| `frontend/public/icon-512.png` | Splash / High-res PWA Icon | 512×512 PNG |
| `frontend/public/site.webmanifest` | Web App Manifest metadata | JSON |

---

## 3. Visual Construction & Grid

- **Base Coordinate Grid:** `24 × 24` square unit system.
- **Stroke Architecture:** `2.3px` stroke width with `stroke-linecap="round"` and `stroke-linejoin="round"`.
- **Symmetry:** Horizontally symmetrical around the `y = 12` center axis.
- **Inlets:** Top channel at `y = 7`, bottom channel at `y = 17` (10 units vertical delta).
- **Convergence Point:** Smooth cubic Bezier transition (`c 3 0 4.5 ±5 7.5 ±5`) merging at `x = 16, y = 12`.
- **Directional Arrow Head:** Extending to `(20.5, 12)` with barb lines returning to `(17, 8.5)` and `(17, 15.5)`.

---

## 4. Typography & Wordmark

- **Typeface:** Inter (`font-family: -apple-system, BlinkMacSystemFont, 'Inter', sans-serif`).
- **Weight:** Semi-bold `600`.
- **Tracking:** `-0.01em` optical kerning.
- **Lockup:** Sits vertically centered next to the brand squircle mark with `gap: 10px`.

---

## 5. Asset Generation Workflow

To regenerate all raster assets from the canonical vector geometry:

```bash
# Requires Python with Pillow and headless Google Chrome
.venv/bin/python scripts/generate_brand_assets.py
```

Assets are automatically mirrored into `dashboard/app/` upon running:

```bash
cd frontend && npm run build
```
