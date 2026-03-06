"""Convert asciicast v2 to animated GIF using Pillow."""
import json, re, os
from PIL import Image, ImageDraw, ImageFont

CHAR_W, CHAR_H, COLS, ROWS, PADDING = 7, 14, 90, 35, 10
BG_COLOR, FG_COLOR, TITLE_BAR = (30, 30, 46), (205, 214, 244), (49, 50, 68)
ANSI_COLORS = {
    "30": (69,71,90), "31": (243,139,168), "32": (166,227,161), "33": (249,226,175),
    "34": (137,180,250), "35": (203,166,247), "36": (148,226,213), "37": (186,194,222),
    "90": (88,91,112), "91": (243,139,168), "92": (166,227,161), "93": (249,226,175),
    "94": (137,180,250), "95": (203,166,247), "96": (148,226,213), "97": (205,214,244),
}

def parse_ansi_line(text):
    segments, color = [], FG_COLOR
    for part in re.split(r'(\033\[[0-9;]*m)', text):
        m = re.match(r'\033\[([0-9;]*)m', part)
        if m:
            for c in m.group(1).split(";"):
                if c in ("0", ""): color = FG_COLOR
                elif c == "2": color = (120, 120, 140)
                elif c in ANSI_COLORS: color = ANSI_COLORS[c]
        elif part:
            segments.append((part, color))
    return segments

def render_frame(lines):
    w, h = COLS*CHAR_W+PADDING*2, ROWS*CHAR_H+PADDING*2+24
    img = Image.new("RGB", (w, h), BG_COLOR)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, w, 23], fill=TITLE_BAR)
    draw.ellipse([10,7,20,17], fill=(243,139,168))
    draw.ellipse([25,7,35,17], fill=(249,226,175))
    draw.ellipse([40,7,50,17], fill=(166,227,161))
    try: font = ImageFont.truetype("consola.ttf", 11)
    except: font = ImageFont.load_default()
    draw.text((60, 5), "FinMind - Savings Tracking Demo", fill=FG_COLOR, font=font)
    y = 24 + PADDING
    for i, line in enumerate(lines[-ROWS:]):
        x = PADDING
        for text, color in parse_ansi_line(line):
            draw.text((x, y + i*CHAR_H), text, fill=color, font=font)
            x += len(text) * CHAR_W
    return img

def main():
    with open("demo_133.cast", "r", encoding="utf-8") as f:
        lines_raw = f.readlines()
    events = [json.loads(l) for l in lines_raw[1:] if l.strip()]
    screen_text, frames, frame_times = "", [], []
    next_sample = 0
    for ts, etype, data in events:
        if etype != "o": continue
        screen_text += data
        if ts >= next_sample:
            frames.append(screen_text.split("\n"))
            frame_times.append(ts)
            next_sample = ts + 0.3
    frames.append(screen_text.split("\n"))
    frame_times.append(events[-1][0] if events else 0)
    print(f"Generating {len(frames)} frames...")
    images = [render_frame(f) for f in frames]
    durations = [max(25, min(int((frame_times[i+1]-frame_times[i])*500), 1000)) for i in range(len(frame_times)-1)] + [3000]
    images[0].save("demo_savings.gif", save_all=True, append_images=images[1:], duration=durations, loop=0, optimize=True)
    print(f"GIF saved: demo_savings.gif ({os.path.getsize('demo_savings.gif')/1024:.0f} KB, {len(images)} frames)")

if __name__ == "__main__":
    main()
