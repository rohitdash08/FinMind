"""Record demo as asciicast v2 format."""
import json
import os
import subprocess
import time

MAIN_PYTHON = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "FinMind", "packages", "backend", ".venv", "Scripts", "python.exe"
))

def record_asciicast(output_file="demo_124.cast"):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "LOG_LEVEL": "CRITICAL", "TERM": "xterm-256color"}
    python_exe = MAIN_PYTHON

    proc = subprocess.Popen(
        [python_exe, "demo_login_anomaly.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=env,
    )

    start = time.time()
    header = {
        "version": 2,
        "width": 100,
        "height": 40,
        "timestamp": int(start),
        "env": {"SHELL": "/bin/bash", "TERM": "xterm-256color"}
    }

    events = []
    buffer = b""

    while True:
        chunk = proc.stdout.read(1)
        if not chunk:
            break
        buffer += chunk
        if chunk == b"\n" or len(buffer) > 200:
            elapsed = time.time() - start
            try:
                text = buffer.decode("utf-8", errors="replace")
                events.append([round(elapsed, 6), "o", text])
            except Exception:
                pass
            buffer = b""

    if buffer:
        elapsed = time.time() - start
        events.append([round(elapsed, 6), "o", buffer.decode("utf-8", errors="replace")])

    proc.wait()

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(json.dumps(header) + "\n")
        for event in events:
            f.write(json.dumps(event) + "\n")

    print(f"Recorded {len(events)} events to {output_file}")
    return output_file


if __name__ == "__main__":
    cast = record_asciicast()
    print(f"Cast file saved at: {cast}")
