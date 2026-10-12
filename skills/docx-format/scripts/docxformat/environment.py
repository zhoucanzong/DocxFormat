"""Read-only environment evidence; never silently substitute requested fonts."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

from .package import digest


def preflight(profile, *, fc_match=None, fontconfig=None, renderer=None):
    names = set()
    for spec in profile.get("roles", {}).values():
        names.update(v for k, v in spec.get("run", {}).items() if k in {"font_east_asia", "font_latin"})
    tool = fc_match or shutil.which("fc-match")
    env = dict(os.environ)
    if fontconfig:
        env["FONTCONFIG_FILE"] = str(Path(fontconfig).resolve())
    reports = []
    for name in sorted(names):
        item = {"requested": name, "status": "not-verified", "actual_render_binding": "not-verified"}
        if tool:
            try:
                run = subprocess.run([tool, "--format", "%{family}\n%{file}\n%{index}\n", name],
                                     env=env, capture_output=True, text=True, timeout=20)
                lines = run.stdout.splitlines()
                if run.returncode or "Cannot load default config" in run.stderr or len(lines) < 2:
                    item["reason"] = "Fontconfig unavailable or misconfigured"
                    item["diagnostic"] = run.stderr[:500]
                else:
                    families = [f.strip().casefold() for f in lines[0].split(",")]
                    item.update({"matched_family": lines[0], "file": lines[1], "face_index": lines[2] if len(lines) > 2 else "0",
                                 "status": "matched-family" if name.casefold() in families else "fallback-detected"})
                    if Path(lines[1]).is_file():
                        item["font_sha256"] = digest(Path(lines[1]).read_bytes())
            except (OSError, subprocess.TimeoutExpired) as exc:
                item["reason"] = str(exc)
        else:
            item["reason"] = "No font inspection tool supplied; use the target application's font controls"
        reports.append(item)
    return {"fonts": reports, "fontconfig": fontconfig or env.get("FONTCONFIG_FILE"),
            "renderer": renderer, "renderer_exists": bool(renderer and Path(renderer).is_file()),
            "needs_font_decision": any(r["status"] != "matched-family" for r in reports),
            "note": "Family matching/file hashes do not prove actual rendering, glyph coverage or Word/WPS shaping. Inspect rendered pages."}
