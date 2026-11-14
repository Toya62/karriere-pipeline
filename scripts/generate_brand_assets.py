#!/usr/bin/env python3
"""Generate all brand raster and manifest assets from canonical vector designs."""

import json
import os
import subprocess
from pathlib import Path
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DIR = REPO_ROOT / "frontend" / "public"
BRAND_DIR = REPO_ROOT / "frontend" / "src" / "assets" / "brand"
TEMP_DIR = REPO_ROOT / "docs" / "brand"

CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

def render_html_to_png(html_content: str, output_png: Path, width: int, height: int):
    """Render an HTML string to a PNG file using headless Chrome."""
    temp_html = TEMP_DIR / f"_temp_render_{width}x{height}.html"
    temp_html.write_text(html_content, encoding="utf-8")
    
    cmd = [
        CHROME_BIN,
        "--headless",
        f"--screenshot={output_png}",
        f"--window-size={width},{height}",
        "--default-background-color=00000000",
        f"file://{temp_html.resolve()}"
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if temp_html.exists():
        temp_html.unlink()

def main():
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    BRAND_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    print("1. Rendering master icon-512.png...")
    html_512 = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body {
    width: 512px;
    height: 512px;
    overflow: hidden;
    background: transparent;
  }
  .app-icon {
    width: 512px;
    height: 512px;
    border-radius: 112px;
    background: linear-gradient(145deg, #2563eb 0%, #1d4ed8 50%, #1e40af 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: inset 0 2px 4px rgba(255, 255, 255, 0.25);
  }
  svg {
    width: 300px;
    height: 300px;
    color: #ffffff;
    filter: drop-shadow(0 6px 16px rgba(15, 23, 42, 0.3));
  }
</style>
</head>
<body>
  <div class="app-icon">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round">
      <path d="M 3.5 7 h 5 c 3 0 4.5 5 7.5 5 h 4.5" />
      <path d="M 3.5 17 h 5 c 3 0 4.5 -5 7.5 -5" />
      <path d="M 17 8.5 L 20.5 12 L 17 15.5" />
    </svg>
  </div>
</body>
</html>"""
    
    icon_512_path = PUBLIC_DIR / "logo-512.png"
    render_html_to_png(html_512, icon_512_path, 512, 512)
    # Also write icon-512.png per PWA manifest convention
    pwa_512_path = PUBLIC_DIR / "icon-512.png"
    render_html_to_png(html_512, pwa_512_path, 512, 512)
    print(f"Generated {icon_512_path} and {pwa_512_path}")

    print("2. Generating responsive icons from 512 master...")
    img_512 = Image.open(icon_512_path)

    # 192x192 for PWA
    img_192 = img_512.resize((192, 192), Image.Resampling.LANCZOS)
    img_192.save(PUBLIC_DIR / "icon-192.png", "PNG", optimize=True)
    print("Generated icon-192.png")

    # 180x180 for iOS Apple Touch Icon
    img_180 = img_512.resize((180, 180), Image.Resampling.LANCZOS)
    img_180.save(PUBLIC_DIR / "apple-touch-icon.png", "PNG", optimize=True)
    print("Generated apple-touch-icon.png")

    print("3. Rendering high-precision favicons (32x32 and 16x16)...")
    html_32 = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body {
    width: 32px;
    height: 32px;
    overflow: hidden;
    background: transparent;
  }
  .fav-icon {
    width: 32px;
    height: 32px;
    border-radius: 7px;
    background: linear-gradient(145deg, #3b82f6 0%, #2563eb 100%);
    display: flex;
    align-items: center;
    justify-content: center;
  }
  svg {
    width: 20px;
    height: 20px;
    color: #ffffff;
  }
</style>
</head>
<body>
  <div class="fav-icon">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round">
      <path d="M 3.5 7 h 5 c 3 0 4.5 5 7.5 5 h 4.5" />
      <path d="M 3.5 17 h 5 c 3 0 4.5 -5 7.5 -5" />
      <path d="M 17 8.5 L 20.5 12 L 17 15.5" />
    </svg>
  </div>
</body>
</html>"""
    
    fav_32_path = PUBLIC_DIR / "favicon-32x32.png"
    render_html_to_png(html_32, fav_32_path, 32, 32)
    print("Generated favicon-32x32.png")

    # 16x16 favicon
    img_32 = Image.open(fav_32_path)
    img_16 = img_32.resize((16, 16), Image.Resampling.LANCZOS)
    fav_16_path = PUBLIC_DIR / "favicon-16x16.png"
    img_16.save(fav_16_path, "PNG", optimize=True)
    print("Generated favicon-16x16.png")

    # Multi-resolution favicon.ico (16x16 and 32x32)
    ico_path = PUBLIC_DIR / "favicon.ico"
    img_32.save(ico_path, format="ICO", sizes=[(16, 16), (32, 32)])
    print(f"Generated multi-res ICO {ico_path}")

    print("4. Generating site.webmanifest...")
    manifest = {
        "name": "Karriere Pipeline",
        "short_name": "KarrierePipeline",
        "description": "Automated Job Intelligence & Precision Application Pipeline",
        "start_url": "/app/",
        "display": "standalone",
        "background_color": "#090d16",
        "theme_color": "#2563eb",
        "icons": [
            {
                "src": "/favicon.svg",
                "sizes": "any",
                "type": "image/svg+xml"
            },
            {
                "src": "/favicon-32x32.png",
                "sizes": "32x32",
                "type": "image/png"
            },
            {
                "src": "/icon-192.png",
                "sizes": "192x192",
                "type": "image/png"
            },
            {
                "src": "/icon-512.png",
                "sizes": "512x512",
                "type": "image/png"
            },
            {
                "src": "/icon-512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "maskable"
            }
        ]
    }
    manifest_path = PUBLIC_DIR / "site.webmanifest"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Generated {manifest_path}")

if __name__ == "__main__":
    main()
