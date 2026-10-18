"""A local web studio for image and video generation. The server logs and saves nothing.

The server keeps no prompt or result after a request. Image edits and video runs
use temporary files for references and output, then remove them. The browser
keeps results until Clear all, unless "Keep in this browser" is off. The server
binds 127.0.0.1 by default. The page loads htmx and Lit from CDNs. Neither gets
prompt data.

USAGE:
    uv run studio                      # http://127.0.0.1:8765, official Qwen Turbo
    uv run studio --port 9000
    uv run studio --backend qwen21 -q 8
    uv run studio --stub --port 8832   # the page on fake engines, for page work
"""

import argparse
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path

from studio.l3_interface_adapters.gateways.qwen21.rewriter import cache_line
from studio.l4_frameworks_and_drivers.config import Config, ConfigError, load_config
from studio.l4_frameworks_and_drivers.engines import EngineUnavailable
from studio.l4_frameworks_and_drivers.main import REWRITERS, create_studio, qwen21_rewrite_models

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "studio.toml"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Serve a local multimedia generation studio. The server logs and saves nothing."
    )
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


def rewriter_cache_line(config: Config) -> str:
    """What the page's rewriters will have to fetch, or "" when it has none.

    The line belongs beside the loading one, before the click rather than during
    it: the first rewrite in a mode fetches about 19 GB with the terminal kept
    quiet, so the button looks merely busy for minutes.
    """
    backend_id = config.default_backend
    models = qwen21_rewrite_models(config, backend_id) if backend_id in REWRITERS else None
    return cache_line(models) if models else ""


def main():
    args = parse_args()
    try:
        config = load_config(args.config, backend=args.backend, quantize=args.quantize)
        studio = create_studio(config, stub=args.stub)
    except ConfigError as error:
        sys.exit(f"Bad settings in {args.config}: {error}")
    except EngineUnavailable as error:
        sys.exit(f"Cannot run here: {error}")
    # Bind before loading. The weights take a minute, and a busy port found
    # after that minute is a waste. Anything that connects during the load
    # waits in the listen backlog.
    try:
        server = ThreadingHTTPServer((args.host, args.port), studio.handler)
    except OSError as error:
        sys.exit(f"Cannot bind {args.host}:{args.port} ({error}). Pass --port for a free one.")
    rewriters = rewriter_cache_line(config)
    if rewriters:
        print(rewriters, flush=True)
    print(f"\nReady on http://{args.host}:{args.port}", flush=True)
    print(
        "Models load on first use. Switching workspaces releases inactive model memory. Ctrl-C to stop.\n",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        studio.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
