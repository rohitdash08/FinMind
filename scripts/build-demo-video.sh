#!/usr/bin/env sh
set -eu

ARTIFACT_DIR="${1:-tmp/demo_build}"
OUTPUT_FILE="${2:-docs/demo/finmind-deploy-demo.mp4}"
WORK_DIR="${ARTIFACT_DIR}/video_work"

LOGIN_IMAGE="docs/demo/review-login.png"
DASHBOARD_IMAGE="docs/demo/review-dashboard.png"
FONT_TITLE="/System/Library/Fonts/Supplemental/Arial Bold.ttf"
FONT_BODY="/System/Library/Fonts/SFNSMono.ttf"

mkdir -p "$WORK_DIR"

if [ ! -f "$ARTIFACT_DIR/compose-ps.txt" ] || [ ! -f "$ARTIFACT_DIR/review-checks.txt" ]; then
  echo "Missing review artifact text files in $ARTIFACT_DIR" >&2
  exit 1
fi

if [ ! -f "$LOGIN_IMAGE" ] || [ ! -f "$DASHBOARD_IMAGE" ]; then
  echo "Missing demo screenshots under docs/demo/" >&2
  exit 1
fi

python3 - "$ARTIFACT_DIR" "$WORK_DIR" "$LOGIN_IMAGE" "$DASHBOARD_IMAGE" "$FONT_TITLE" "$FONT_BODY" <<'PY'
from pathlib import Path
import sys
from PIL import Image, ImageDraw, ImageFont


artifact_dir = Path(sys.argv[1])
work_dir = Path(sys.argv[2])
login_image = Path(sys.argv[3])
dashboard_image = Path(sys.argv[4])
font_title = sys.argv[5]
font_body = sys.argv[6]

W, H = 1280, 720


def load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def draw_multiline(draw: ImageDraw.ImageDraw, text: str, font, fill, x: int, y: int, line_gap: int = 10):
    cursor = y
    for line in text.splitlines():
        draw.text((x, cursor), line, font=font, fill=fill)
        cursor += font.size + line_gap


def render_card(name: str, title: str, body: str, *, bg: str, title_color: str = "#ffffff", body_color: str = "#dbeafe"):
    image = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(image)
    title_font = load_font(font_title, 42)
    body_font = load_font(font_body, 24)
    draw.text((72, 54), title, font=title_font, fill=title_color)
    draw_multiline(draw, body, body_font, body_color, 72, 140, 12)
    image.save(work_dir / name)


def render_labeled_screenshot(source: Path, name: str, title: str):
    base = Image.new("RGB", (W, H), "#06101b")
    shot = Image.open(source).convert("RGB")
    shot.thumbnail((W - 120, H - 160))
    x = (W - shot.width) // 2
    y = 100 + (H - 140 - shot.height) // 2
    base.paste(shot, (x, y))
    draw = ImageDraw.Draw(base)
    title_font = load_font(font_title, 30)
    draw.rectangle((0, 0, W, 84), fill="#06101b")
    draw.text((60, 24), title, font=title_font, fill="#ffffff")
    base.save(work_dir / name)


compose_body = (artifact_dir / "compose-ps.txt").read_text(encoding="utf-8").strip()
checks_body = (artifact_dir / "review-checks.txt").read_text(encoding="utf-8").strip()

render_card(
    "01-title.png",
    "FinMind deployment review path",
    "One-command verification, explicit dependency readiness,\nand a downloadable review artifact bundle for maintainer re-checks.",
    bg="#09111f",
)
render_card(
    "02-compose.png",
    "Healthy services snapshot",
    compose_body,
    bg="#0f172a",
)
render_card(
    "03-checks.png",
    "Readiness and observability checks",
    checks_body,
    bg="#111827",
    body_color="#d1fae5",
)
render_labeled_screenshot(login_image, "04-login.png", "Login flow available on the deployed app")
render_labeled_screenshot(dashboard_image, "05-dashboard.png", "Dashboard state after successful auth")
render_card(
    "06-free-tier.png",
    "Free-tier deployment entrypoints included",
    "Render: render.yaml\nNetlify: netlify.toml\nVercel: vercel.json\nMaintainer quick path: ./scripts/review-deploy.sh",
    bg="#071521",
    body_color="#fef3c7",
)
PY

ffmpeg -y -loop 1 -t 4 -i "$WORK_DIR/01-title.png" -c:v libx264 -pix_fmt yuv420p "$WORK_DIR/01-title.mp4" >/dev/null 2>&1
ffmpeg -y -loop 1 -t 8 -i "$WORK_DIR/02-compose.png" -c:v libx264 -pix_fmt yuv420p "$WORK_DIR/02-compose.mp4" >/dev/null 2>&1
ffmpeg -y -loop 1 -t 8 -i "$WORK_DIR/03-checks.png" -c:v libx264 -pix_fmt yuv420p "$WORK_DIR/03-checks.mp4" >/dev/null 2>&1
ffmpeg -y -loop 1 -t 6 -i "$WORK_DIR/04-login.png" -c:v libx264 -pix_fmt yuv420p "$WORK_DIR/04-login.mp4" >/dev/null 2>&1
ffmpeg -y -loop 1 -t 8 -i "$WORK_DIR/05-dashboard.png" -c:v libx264 -pix_fmt yuv420p "$WORK_DIR/05-dashboard.mp4" >/dev/null 2>&1
ffmpeg -y -loop 1 -t 6 -i "$WORK_DIR/06-free-tier.png" -c:v libx264 -pix_fmt yuv420p "$WORK_DIR/06-free-tier.mp4" >/dev/null 2>&1

cat > "$WORK_DIR/concat.txt" <<EOF
file '01-title.mp4'
file '02-compose.mp4'
file '03-checks.mp4'
file '04-login.mp4'
file '05-dashboard.mp4'
file '06-free-tier.mp4'
EOF

ffmpeg -y -f concat -safe 0 -i "$WORK_DIR/concat.txt" -c copy "$OUTPUT_FILE" >/dev/null 2>&1

printf '%s\n' "Updated demo video: $OUTPUT_FILE"
