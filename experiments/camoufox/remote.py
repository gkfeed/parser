"""Experimental loopback-only remote server using the pinned launch options."""

import importlib
import os

from spike import launch_options, parse_args

args = parse_args()
if args.engine != "camoufox" or not args.binary or args.remote:
    raise ValueError("Server requires --engine camoufox --binary PATH --output PATH")
server = importlib.import_module("camoufox.server")
args.output.mkdir(parents=True, exist_ok=False)
(args.output / "server.pid").write_text(str(os.getpid()))
server.launch_server(
    **launch_options(args), host="127.0.0.1", port=19313, ws_path="p13"
)
