"""Title cleanup and YouTube video ID parsing helpers for TV AutoSEO."""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse


def clean_video_title(value: str) -> str:
    title = " ".join(str(value or "").replace("<", "").replace(">", "").split())
    # Stay within 100 UTF-16 units, keeping emoji/surrogate pairs whole.
    title = title.encode("utf-16-le")[:200].decode("utf-16-le", errors="ignore").strip()
    if not title:
        raise ValueError("Tên file nhạc không tạo được tiêu đề hợp lệ.")
    return title


def parse_manual_title_ids(text: str) -> list[str]:
    """Accept explicit IDs or YouTube links, preserving order without duplicates."""
    identifiers = []
    seen = set()
    for index, value in enumerate(re.split(r"[\s,;]+", str(text or "").strip()), 1):
        if not value:
            continue
        identifier = value
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", identifier):
            try:
                url = urlparse(value if "://" in value else "https://" + value)
            except ValueError:
                raise ValueError(f"Mục {index} không phải Video ID hoặc link YouTube hợp lệ.") from None
            host = (url.hostname or "").lower()
            parts = url.path.strip("/").split("/")
            identifier = ""
            if url.scheme in {"http", "https"}:
                if host in {"youtu.be", "www.youtu.be"} and len(parts) == 1:
                    identifier = parts[0]
                elif host in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "studio.youtube.com"}:
                    if parts == ["watch"]:
                        identifier = parse_qs(url.query).get("v", [""])[0]
                    elif len(parts) >= 2 and parts[0] in {"video", "shorts", "live", "embed"}:
                        identifier = parts[1]
            if not re.fullmatch(r"[A-Za-z0-9_-]{11}", identifier):
                raise ValueError(f"Mục {index} không phải Video ID hoặc link YouTube hợp lệ. Mỗi Video ID có 11 ký tự.")
        if identifier not in seen:
            seen.add(identifier)
            identifiers.append(identifier)
        if len(identifiers) > 10_000:
            raise ValueError("Mỗi lượt chỉ đọc tối đa 10.000 Video ID.")
    if not identifiers:
        raise ValueError("Nhập ít nhất một Video ID hoặc link YouTube.")
    return identifiers
