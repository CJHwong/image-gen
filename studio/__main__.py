"""A local web page for image generation. Nothing is logged or saved.

The prompt never reaches disk, and neither does the image: it goes from the
engine to the page as an in-page data URL, so no EXIF or prompt text is
embedded either. The page keeps this session's images in tab memory, so a
reload clears them. The server binds 127.0.0.1 by default. Its one outbound
request is the htmx script from a CDN, which carries no prompt data.

USAGE:
    uv run studio                      # http://127.0.0.1:8765, the default backend
    uv run studio --port 9000
    uv run studio --backend qwen21 -q 8
    uv run studio --stub --port 8832   # the page on fake engines, for page work
"""

import argparse
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path

from studio.l4_frameworks_and_drivers.config import ConfigError, load_config
from studio.l4_frameworks_and_drivers.main import create_studio

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "studio.toml"


def parse_args():
    parser = argparse.ArgumentParser(description="Serve a local image generation page. Nothing is logged or saved.")
    parser.add_argument("--host", default="127.0.0.1", help="bind address (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="port (default 8765)")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="settings file (default studio.toml)")
    parser.add_argument("--backend", help="open on this backend instead of the configured default")
    parser.add_argument(
        "-q",
        "--quantize",
        type=int,
        choices=[3, 4, 5, 6, 8],
        help="quantize the weights of the backend the page opens with; omit for the studio.toml setting",
    )
    parser.add_argument(
        "--stub",
        action="store_true",
        help="fake every engine: timed steps and placeholder images, no weights, no GPU. For work on the page",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        studio = create_studio(load_config(args.config, backend=args.backend, quantize=args.quantize), stub=args.stub)
    except ConfigError as error:
        sys.exit(f"Bad settings in {args.config}: {error}")
    # Bind before loading. The weights take a minute, and a busy port found
    # after that minute is a waste. Anything that connects during the load
    # waits in the listen backlog.
    try:
        server = ThreadingHTTPServer((args.host, args.port), studio.handler)
    except OSError as error:
        sys.exit(f"Cannot bind {args.host}:{args.port} ({error}). Pass --port for a free one.")
    capabilities = studio.active_capabilities()
    print(f"Loading {capabilities.name} ({capabilities.badge}). The first run may download the weights.", flush=True)
    try:
        studio.prepare.execute()
    except Exception as error:
        sys.exit(f"Could not load the model: {error}")
    print(f"\nReady on http://{args.host}:{args.port}", flush=True)
    print("Nothing is written to disk. Ctrl-C to stop.\n", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        studio.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
