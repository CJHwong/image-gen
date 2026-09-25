"""A stand-in engine child: one JSON job per line in, one JSON answer per line out.

The job says how to behave: how many steps, how long each takes, and whether to
fail, crash or answer. Its pid goes to stderr so a test can check it died.
"""

import json
import os
import sys
import time

print(f"pid {os.getpid()}", file=sys.stderr, flush=True)
for line in sys.stdin:
    job = json.loads(line)
    if job.get("say"):
        print(f"say {job['say']}", file=sys.stderr, flush=True)
    for step in range(job.get("steps", 2) + 1):  # step 0 first, as the real child
        time.sleep(job.get("pause", 0))
        print(f"step {step}/{job.get('steps', 2)}", file=sys.stderr, flush=True)
    if job.get("crash"):
        sys.exit(3)
    if job.get("error"):
        print(json.dumps({"error": job["error"]}), flush=True)
        continue
    print(json.dumps({"echo": job.get("echo"), "pid": os.getpid()}), flush=True)
    if job.get("exit"):
        sys.exit(0)  # the engine goes, and a survivor may keep its pipes
