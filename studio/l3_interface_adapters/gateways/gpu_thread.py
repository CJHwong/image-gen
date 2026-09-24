"""Every model call runs on one thread.

MLX binds GPU streams to the thread that created them, and the HTTP server
answers each request on a fresh thread. Calling the model from a request thread
aborts the process with "There is no Stream(gpu, 1) in current thread". So
request threads hand their call to this one thread and wait for the answer.
"""

import queue
import threading


class GpuThread:
    def __init__(self):
        self._calls = queue.Queue()
        threading.Thread(target=self._serve, daemon=True, name="gpu").start()

    def call(self, function, *args):
        """Run `function(*args)` on the GPU thread. Blocks until it returns or raises."""
        done = threading.Event()
        outcome = {}
        self._calls.put((function, args, outcome, done))
        done.wait()
        if "error" in outcome:
            raise outcome["error"]
        return outcome.get("value")

    def _serve(self):
        while True:
            function, args, outcome, done = self._calls.get()
            try:
                outcome["value"] = function(*args)
            except BaseException as error:  # handed back to the caller, who raises it
                outcome["error"] = error
            finally:
                done.set()
