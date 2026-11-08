"""Build code-native application icon and consistent 1.7px SVG glyphs."""
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
(ASSETS / "icons").mkdir(parents=True, exist_ok=True)
paths = {
    "download": '<path d="M12 3v12m-5-5 5 5 5-5M4 15v5h16v-5"/>',
    "video": '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="m10 9 5 3-5 3z"/>',
    "settings": '<path d="m9 3-1 3-3 1 1 3-2 2 2 2-1 3 3 1 1 3h6l1-3 3-1-1-3 2-2-2-2 1-3-3-1-1-3z"/><circle cx="12" cy="12" r="3"/>',
    "clipboard": '<rect x="5" y="5" width="14" height="16" rx="2"/><rect x="9" y="3" width="6" height="4" rx="1"/>',
    "folder": '<path d="M3 7V5h6l2 3h10v12H3z"/>',
    "link": '<path d="m10 14 4-4m-7 3-2 2a4 4 0 0 0 6 6l4-4a4 4 0 0 0 0-6m2 0 2-2a4 4 0 0 0-6-6L9 7a4 4 0 0 0 0 6"/>',
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    "inbox": '<path d="m5 4-3 11v5h20v-5L19 4zM2 15h6l2 3h4l2-3h6"/>',
    "refresh": '<path d="M20 7v5h-5M4 17v-5h5M5 8a8 8 0 0 1 13-3l2 2M4 17l2 2a8 8 0 0 0 13-3"/>',
    "shield": '<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6zM8 12l3 3 5-6"/>',
    "alert-circle": '<circle cx="12" cy="12" r="9"/><path d="M12 7v6m0 3v1"/>',
    "trash": '<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7"/>',
}
for name, path in paths.items():
    (ASSETS / "icons" / (name + ".svg")).write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#aebbd0" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{path}</svg>')
size = 512
image = Image.new("RGBA", (size, size))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((16, 16, 496, 496), radius=116, fill="#1b2534")
draw.rounded_rectangle((48, 48, 464, 464), radius=88, outline="#405773", width=3)
draw.line([(256, 116), (256, 308)], fill="#95bfff", width=30)
draw.line([(174, 234), (256, 316), (338, 234)], fill="#95bfff", width=30, joint="curve")
draw.line([(140, 320), (140, 382), (372, 382), (372, 320)], fill="#e4edfa", width=24, joint="curve")
image.save(ASSETS / "app.png")
image.save(ASSETS / "app.ico", sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
