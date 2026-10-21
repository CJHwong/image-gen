"""A stand-in engine child: one JSON job per line in, one JSON answer per line out.

The job says how to behave: how many steps, how long each takes, and whether to
fail, crash or answer. Its pid goes to stderr so a test can check it died.
"""

import json
import os
import sys
import time
from pathlib import Path

print(f"pid {os.getpid()}", file=sys.stderr, flush=True)
print("ready", file=sys.stderr, flush=True)  # the real child says it once its engine is loaded
for line in sys.stdin:
    job = json.loads(line)
    if job.get("say"):
        print(f"say {job['say']}", file=sys.stderr, flush=True)
    for step in range(job.get("steps", 2) + 1):  # step 0 first, as the real child
        time.sleep(job.get("pause", 0))
        print(f"step {step}/{job.get('steps', 2)}", file=sys.stderr, flush=True)
    if job.get("noise"):
        print(job["noise"], flush=True)  # an engine library printing on stdout
    if job.get("crash"):
        sys.exit(3)
    if job.get("error"):
        print(json.dumps({"error": job["error"], "kind": job.get("kind", "engine")}), flush=True)
        continue
    if job.get("write_scratch"):  # a clip on disk, where the protocol says to put it
        (Path(os.environ["SPEECH_GEN_SCRATCH"]) / "ref.wav").write_bytes(b"voice")
    print(json.dumps({"echo": job.get("echo"), "pid": os.getpid()}), flush=True)
    if job.get("exit"):
        sys.exit(0)  # the engine goes, and a survivor may keep its pipes
