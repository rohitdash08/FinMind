"""Convert asciicast v2 to animated GIF using Pillow."""
import json
import re
import sys
import os
from PIL import Image, ImageDraw, ImageFont

CHAR_W = 7
CHAR_H = 14
COLS = 90
ROWS = 35
PADDING = 10
BG_COLOR = (30, 30, 46)
FG_COLOR = (205, 214, 244)
TITLE_BAR = (49, 50, 68)

ANSI_COLORS = {
    "30": (69, 71, 90), "31": (243, 139, 168), "32": (166, 227, 161),
    "33": (249, 226, 175), "34": (137, 180, 250), "35": (203, 166, 247),
    "36": (148, 226, 213), "37": (186, 194, 222),
    "90": (88, 91, 112), "91": (243, 139, 168), "92": (166, 227, 161),
    "93": (249, 226, 175), "94": (137, 180, 250), "95": (203, 166, 247),
    "96": (148, 226, 213), "97": (205, 214, 244),
}


def parse_ansi_line(text):
    segments = []
    current_color = FG_COLOR
    parts = re.split(r'(\033\[[0-9;]*m)', text)
    for part in parts:
        m = re.match(r'\033\[([0-9;]*)m', part)
        if m:
            codes = m.group(1).split(";")
            for code in codes:
                if code == "0" or code == "":
                    current_color = FG_COLOR
                elif code == "1":
                    pass
                elif code == "2":
                    current_color = (120, 120, 140)
                elif code in ANSI_COLORS:
                    current_color = ANSI_COLORS[code]
        else:
            if part:
                segments.append((part, current_color))
    return segments


def render_frame(lines):
    width = COLS * CHAR_W + PADDING * 2
    height = ROWS * CHAR_H + PADDING * 2 + 24

    img = Image.new("RGB", (width, height), BG_COLOR)
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, width, 23], fill=TITLE_BAR)
    draw.ellipse([10, 7, 20, 17], fill=(243, 139, 168))
    draw.ellipse([25, 7, 35, 17], fill=(249, 226, 175))
    draw.ellipse([40, 7, 50, 17], fill=(166, 227, 161))

    try:
        font = ImageFont.truetype("consola.ttf", 11)
    except Exception:
        font = ImageFont.load_default()
    draw.text((60, 5), "FinMind - Shared Household Budgeting Demo", fill=(205, 214, 244), font=font)

    try:
        mono = ImageFont.truetype("consola.ttf", 11)
    except Exception:
        mono = ImageFont.load_default()

    y_offset = 24 + PADDING
    for i, line in enumerate(lines[-ROWS:]):
        x = PADDING
        segments = parse_ansi_line(line)
        for text, color in segments:
            draw.text((x, y_offset + i * CHAR_H), text, fill=color, font=mono)
            x += len(text) * CHAR_W

    return img


def main():
    cast_file = "demo_134.cast"
    gif_file = "demo_shared_budgets.gif"

    with open(cast_file, "r", encoding="utf-8") as f:
        lines_raw = f.readlines()

    header = json.loads(lines_raw[0])
    events = [json.loads(l) for l in lines_raw[1:] if l.strip()]

    screen_text = ""
    frames = []
    frame_times = []
    sample_interval = 0.3
    next_sample = 0

    for ts, etype, data in events:
        if etype != "o":
            continue
        screen_text += data
        if ts >= next_sample:
            screen_lines = screen_text.split("\n")
            frames.append(list(screen_lines))
            frame_times.append(ts)
            next_sample = ts + sample_interval

    screen_lines = screen_text.split("\n")
    frames.append(list(screen_lines))
    frame_times.append(events[-1][0] if events else 0)

    print(f"Generating {len(frames)} frames...")

    images = []
    for i, frame_lines in enumerate(frames):
        img = render_frame(frame_lines)
        images.append(img)
        if i % 20 == 0:
            print(f"  Frame {i}/{len(frames)}")

    durations = []
    for i in range(len(frame_times) - 1):
        dt = (frame_times[i + 1] - frame_times[i]) * 1000
        dt = max(50, min(dt, 2000))
        durations.append(int(dt / 2))
    durations.append(3000)

    images[0].save(
        gif_file,
        save_all=True,
        append_images=images[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )

    size = os.path.getsize(gif_file)
    print(f"GIF saved: {gif_file} ({size / 1024:.0f} KB, {len(images)} frames)")


if __name__ == "__main__":
    main()
