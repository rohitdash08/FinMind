"""Record demo as asciicast v2 format."""
import json, os, subprocess, time

PYTHON = os.path.join("packages", "backend", ".venv", "Scripts", "python.exe")

def record_asciicast(output_file="demo_132.cast"):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "LOG_LEVEL": "CRITICAL", "TERM": "xterm-256color"}
    proc = subprocess.Popen(
        [PYTHON, "demo_accounts.py"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env,
    )
    start = time.time()
    header = {"version": 2, "width": 100, "height": 40, "timestamp": int(start),
              "env": {"SHELL": "/bin/bash", "TERM": "xterm-256color"}}
    events, buffer = [], b""
    while True:
        chunk = proc.stdout.read(1)
        if not chunk:
            break
        buffer += chunk
        if chunk == b"\n" or len(buffer) > 200:
            events.append([round(time.time() - start, 6), "o", buffer.decode("utf-8", errors="replace")])
            buffer = b""
    if buffer:
        events.append([round(time.time() - start, 6), "o", buffer.decode("utf-8", errors="replace")])
    proc.wait()
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(json.dumps(header) + "\n")
        for event in events:
            f.write(json.dumps(event) + "\n")
    print(f"Recorded {len(events)} events to {output_file}")

if __name__ == "__main__":
    record_asciicast()
