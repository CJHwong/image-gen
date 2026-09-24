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
    for step in range(1, job.get("steps", 2) + 1):
        time.sleep(job.get("pause", 0))
        print(f"step {step}/{job.get('steps', 2)}", file=sys.stderr, flush=True)
    if job.get("crash"):
        sys.exit(3)
    if job.get("error"):
        print(json.dumps({"error": job["error"]}), flush=True)
        continue
    print(json.dumps({"echo": job.get("echo"), "pid": os.getpid()}), flush=True)
