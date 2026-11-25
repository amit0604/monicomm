"""Air-gap guard: fail if source code references the internet.

Scans the app source (not docs, not lock files) for:
  - URLs to public hosts (anything that isn't localhost, a Docker service name or a private IP)
  - known cloud AI / CDN / web-font hosts
Run: python scripts/check_airgap.py   (exit code 1 = violations found)

To allow a specific line on purpose (for example a test that checks a URL is refused), add the
comment `airgap: allow` on that line.
"""

import ipaddress
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = ["api/app", "web/src", "web/index.html", "web/nginx.conf", "collector"]
EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".css", ".html", ".conf", ".json"}
URL_RE = re.compile(r"""(?:https?|wss?)://([A-Za-z0-9.\-]+)""")
FORBIDDEN_HOSTS = re.compile(
    r"(openai\.com|anthropic\.com|googleapis\.com|gstatic\.com|cdnjs|jsdelivr|unpkg\.com|"
    r"huggingface\.co|cloudflare|sentry\.io|segment\.(io|com)|google-analytics)",
    re.IGNORECASE,
)
INTERNAL_SUFFIXES = (".local", ".lan", ".internal", ".localhost")


def is_internal(host: str) -> bool:
    host = host.lower()
    if "." not in host or host.endswith(INTERNAL_SUFFIXES):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_unspecified


def iter_files():
    for entry in SCAN_DIRS:
        path = ROOT / entry
        if path.is_file():
            yield path
        elif path.is_dir():
            for f in path.rglob("*"):
                if f.suffix in EXTENSIONS and "node_modules" not in f.parts:
                    yield f


def main() -> int:
    problems = []
    for f in iter_files():
        for n, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if "airgap: allow" in line:
                continue
            if FORBIDDEN_HOSTS.search(line):
                problems.append((f, n, "forbidden external host", line.strip()))
                continue
            for host in URL_RE.findall(line):
                if not is_internal(host):
                    problems.append((f, n, f"public URL host '{host}'", line.strip()))
    for f, n, why, line in problems:
        print(f"{f.relative_to(ROOT)}:{n}: {why}\n    {line}")
    if problems:
        print(f"\nAir-gap check FAILED: {len(problems)} problem(s). See PROJECT.md section 5.")
        return 1
    print("Air-gap check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
