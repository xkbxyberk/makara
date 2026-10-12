"""Copy the native UI tests' named screenshots out of the xcresult bundle.

They land next to the web ones in test-results/screenshots/, named as the test named them
(`native-inspect-dark.png`, ...). Crash logs Xcode attaches from unrelated processes are skipped.
Usage: uv run python scripts/export_ui_screenshots.py macos/build/ui-tests.xcresult
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "test-results" / "screenshots"


def main() -> int:
    bundle = Path(sys.argv[1])
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            [
                *("xcrun", "xcresulttool", "export", "attachments"),
                "--path",
                str(bundle),
                "--output-path",
                tmp,
            ],
            check=True,
            capture_output=True,
        )
        manifest = json.loads((Path(tmp) / "manifest.json").read_text())
        OUT.mkdir(parents=True, exist_ok=True)
        count = 0
        for test in manifest:
            for attachment in test.get("attachments", []):
                name = attachment.get("suggestedHumanReadableName", "")
                exported = attachment["exportedFileName"]
                if not name.startswith("native-") or not exported.endswith(".png"):
                    continue
                target = OUT / (name.split("_0_")[0] + ".png")
                shutil.copyfile(Path(tmp) / exported, target)
                count += 1
    print(f"{count} native screenshots in {OUT}")
    return 0 if count else 1


if __name__ == "__main__":
    raise SystemExit(main())
