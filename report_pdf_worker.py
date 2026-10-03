"""Disposable PDF parser. Invoked by report_fetcher, never by Streamlit directly."""
from io import BytesIO
import re
import sys

MAX_BYTES = 4_000_000
MAX_TEXT_CHARS = 250_000


def main() -> int:
    # A small compressed PDF can expand far beyond its download size. Limit
    # address space in the child only; never constrain the app's own process.
    try:
        import resource
        _, hard = resource.getrlimit(resource.RLIMIT_AS)
        limit = 384 * 1024 * 1024
        if hard != resource.RLIM_INFINITY:
            limit = min(limit, hard)
        resource.setrlimit(resource.RLIMIT_AS, (limit, hard))
    except (ImportError, AttributeError, OSError, ValueError):
        pass  # Platforms without RLIMIT_AS still have the parent's timeout.
    try:
        from pypdf import PdfReader
        data = sys.stdin.buffer.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            return 1
        reader = PdfReader(BytesIO(data))
        parts = []
        remaining = MAX_TEXT_CHARS
        for page in reader.pages[:40]:
            text = (page.extract_text() or "")[:remaining]
            parts.append(text)
            remaining -= len(text)
            if remaining <= 0:
                break
        text = re.sub(r"\s+", " ", " ".join(parts)).strip()
        sys.stdout.buffer.write(text.encode("utf-8"))
        return 0
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
