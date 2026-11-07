#!/usr/bin/env python3
"""Load Qing_MCP and print a short overview (no MCP transport)."""

from __future__ import annotations

import json
import sys
import time

from vic3_mcp.session import Vic3Session


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else "Qing_MCP"
    t0 = time.time()
    s = Vic3Session.load(name)
    print(f"loaded {s.save_path.name} in {time.time() - t0:.1f}s  countries={len(s.country_map)}")
    ov = s.overview()
    print(json.dumps(ov, ensure_ascii=False, indent=2, default=str)[:4000])
    print("--- analysis ---")
    an = s.analysis()
    print(json.dumps(an, ensure_ascii=False, indent=2, default=str)[:5000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
