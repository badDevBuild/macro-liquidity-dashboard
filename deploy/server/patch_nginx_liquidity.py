#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path


START = "    # BEGIN macro-liquidity-dashboard"
END = "    # END macro-liquidity-dashboard"


def build_block(url_prefix: str, upstream: str) -> str:
    prefix = "/" + url_prefix.strip("/")
    return f"""{START}
    location = {prefix} {{
        return 301 {prefix}/;
    }}

    location {prefix}/ {{
        proxy_pass {upstream.rstrip('/')}/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 5s;
        proxy_read_timeout 30s;
    }}
{END}

"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Insert the dashboard reverse-proxy block at an explicit Nginx anchor."
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--anchor", required=True)
    parser.add_argument("--url-prefix", default="/liquidity")
    parser.add_argument("--upstream", default="http://127.0.0.1:8877")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = args.config.resolve()
    current = config.read_text(encoding="utf-8")
    if START in current and END in current:
        print("nginx liquidity route already present")
        return 0
    if current.count(args.anchor) != 1:
        raise RuntimeError("expected nginx insertion anchor was not found exactly once")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = config.with_name(f"{config.name}.bak.{stamp}")
    shutil.copy2(config, backup)
    updated = current.replace(
        args.anchor,
        build_block(args.url_prefix, args.upstream) + args.anchor,
        1,
    )
    temporary = config.with_suffix(config.suffix + ".tmp")
    temporary.write_text(updated, encoding="utf-8")
    temporary.chmod(config.stat().st_mode)
    temporary.replace(config)
    print(f"nginx liquidity route added; backup={backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
