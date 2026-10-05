#!/usr/bin/env python3
"""Render Mobitecture branding SVGs to PNG launcher assets and commit-ready paths."""
from pathlib import Path
from io import BytesIO
import cairosvg
from PIL import Image

root = Path(".")
branding = root / "branding"
android = branding / "android"

def render_svg(svg: Path, size: int) -> Image.Image:
    png = cairosvg.svg2png(url=str(svg), output_width=size, output_height=size)
    return Image.open(BytesIO(png)).convert("RGBA")

def save(im: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, format="PNG", optimize=True, compress_level=9)
    print(f"Wrote {path} {path.stat().st_size} bytes")

if (branding / "overhead-icon-vibrant.svg").exists():
    hero_svg = branding / "overhead-icon-vibrant.svg"
    hero_png = branding / "overhead-icon-vibrant.png"
    also_root_icons = True
elif (branding / "skerry-icon-vibrant.svg").exists():
    hero_svg = branding / "skerry-icon-vibrant.svg"
    hero_png = branding / "skerry-icon-vibrant.png"
    also_root_icons = False
elif (branding / "liturgy-icon-vibrant.svg").exists():
    hero_svg = branding / "liturgy-icon-vibrant.svg"
    hero_png = branding / "liturgy-icon-vibrant.png"
    also_root_icons = (root / "manifest.json").exists() or (root / "icon.svg").exists()
else:
    raise SystemExit("No vibrant SVG found under branding/")

for name in ["ic_launcher_background", "ic_launcher_foreground", "ic_launcher_monochrome"]:
    svg = android / f"{name}.svg"
    if svg.exists():
        save(render_svg(svg, 432), android / f"{name}.png")

bg = android / "ic_launcher_background.svg"
fg = android / "ic_launcher_foreground.svg"
if bg.exists() and fg.exists():
    save(Image.alpha_composite(render_svg(bg, 512), render_svg(fg, 512)), android / "playstore-icon-512.png")
else:
    save(render_svg(hero_svg, 512), android / "playstore-icon-512.png")

save(render_svg(hero_svg, 256), hero_png)

if also_root_icons:
    hero = render_svg(hero_svg, 256)
    save(hero, root / "icon.png")
    save(hero, root / "icon-mobitecture.png")

res = root / "app/src/main/res"
if (root / "app").exists():
    for name in ["ic_launcher_background", "ic_launcher_foreground", "ic_launcher_monochrome"]:
        src = android / f"{name}.png"
        if src.exists():
            save(Image.open(src).convert("RGBA"), res / "drawable" / f"{name}.png")
    xml_src = android / "ic_launcher.xml"
    if xml_src.exists():
        dest = res / "mipmap-anydpi-v26" / "ic_launcher.xml"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(xml_src.read_text())
        print(f"Wrote {dest}")
    play = android / "playstore-icon-512.png"
    if play.exists():
        ps = Image.open(play).convert("RGBA")
        for dens, sz in [("mdpi", 48), ("hdpi", 72), ("xhdpi", 96), ("xxhdpi", 144), ("xxxhdpi", 192)]:
            save(ps.resize((sz, sz), Image.Resampling.LANCZOS), res / f"mipmap-{dens}" / "ic_launcher.png")

for pat in ["**/*.png.b64", "**/*.png.b64.part*", "branding/.upload-test-tiny.png"]:
    for p in root.glob(pat):
        p.unlink()
        print(f"Removed {p}")
