"""Load articles.json, build captions, and prepare images for Meta publishing."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from PIL import Image

# Instagram feed image aspect ratio must be between 4:5 and 1.91:1 inclusive.
MIN_RATIO = 4 / 5  # 0.8 (portrait)
MAX_RATIO = 1.91  # landscape
LONG_EDGE = 1080
USER_AGENT = "MakerAtPlay-MetaPublisher/1.0"


@dataclass
class Article:
    slug: str
    title: str
    date: str
    summary: str
    url: str
    image: str
    raw: dict[str, Any]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Article:
        slug = str(data.get("slug", "")).strip()
        if not slug:
            raise ValueError("Article missing slug")
        return cls(
            slug=slug,
            title=str(data.get("title", "")).strip(),
            date=str(data.get("date", "")).strip(),
            summary=str(data.get("summary", "")).strip(),
            url=str(data.get("url", "")).strip(),
            image=str(data.get("image", "")).strip(),
            raw=data,
        )


@dataclass
class ImagePlan:
    """Resolved image sources for Facebook and Instagram."""

    local_path: Path | None
    public_url: str | None
    width: int | None
    height: int | None
    needs_letterbox: bool
    letterboxed_path: Path | None
    notes: list[str]

    @property
    def ratio(self) -> float | None:
        if not self.width or not self.height:
            return None
        return self.width / self.height


def load_articles(path: Path) -> list[Article]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Expected a JSON array in {path}")
    return [Article.from_dict(item) for item in payload]


def absolute_url(value: str, site_base: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if value.startswith(("http://", "https://")):
        return value
    base = site_base.rstrip("/")
    if not value.startswith("/"):
        value = "/" + value
    return base + value


def build_caption(article: Article, site_base: str, hashtags: list[str]) -> str:
    parts = [article.title]
    if article.summary:
        parts.append("")
        parts.append(article.summary)
    link = absolute_url(article.url, site_base)
    if link:
        parts.append("")
        parts.append(link)
    tags = normalize_hashtags(hashtags)
    if tags:
        parts.append("")
        parts.append(" ".join(tags))
    return "\n".join(parts).strip() + "\n"


def normalize_hashtags(hashtags: list[str]) -> list[str]:
    result: list[str] = []
    for tag in hashtags:
        for piece in tag.replace(",", " ").split():
            piece = piece.strip()
            if not piece:
                continue
            if not piece.startswith("#"):
                piece = "#" + piece
            result.append(piece)
    return result


ARTICLE_KINDS = (
    "blog",
    "project",
    "workbench",
    "helper9",
    "linkedin",
    "other",
)

KIND_ALIASES: dict[str, tuple[str, ...]] = {
    # Maker At Play site content only (excludes Helper9, LinkedIn, other).
    "makeratplay": ("blog", "project", "workbench"),
}


def article_kind(article: Article) -> str:
    """Classify an article by its URL prefix / host."""
    url = (article.url or "").strip().lower()
    if url.startswith("/blog/"):
        return "blog"
    if url.startswith("/projects/"):
        return "project"
    if url.startswith("/workbench/"):
        return "workbench"
    if "helper9" in url:
        return "helper9"
    if "linkedin.com" in url or "lnkd.in" in url:
        return "linkedin"
    return "other"


def parse_kinds(values: list[str] | None) -> set[str] | None:
    """Expand comma-separated kind tokens and aliases into a set of concrete kinds."""
    if not values:
        return None
    resolved: set[str] = set()
    for raw in values:
        for piece in raw.replace(",", " ").split():
            token = piece.strip().lower()
            if not token:
                continue
            if token in KIND_ALIASES:
                resolved.update(KIND_ALIASES[token])
                continue
            if token not in ARTICLE_KINDS:
                known = ", ".join(ARTICLE_KINDS)
                aliases = ", ".join(KIND_ALIASES)
                raise SystemExit(
                    f"Unknown kind {token!r}. Valid kinds: {known}. Aliases: {aliases}."
                )
            resolved.add(token)
    return resolved


def select_articles(
    articles: list[Article],
    *,
    slug: str | None = None,
    date: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    kinds: set[str] | None = None,
    exclude_kinds: set[str] | None = None,
) -> list[Article]:
    selected = list(articles)

    if slug:
        selected = [article for article in selected if article.slug == slug]
        if not selected:
            raise SystemExit(f"No article found with slug {slug!r}")

    if date:
        selected = [article for article in selected if article.date == date]
        if not selected:
            raise SystemExit(f"No article found for date {date}")

    if from_date:
        selected = [article for article in selected if article.date >= from_date]
    if to_date:
        selected = [article for article in selected if article.date <= to_date]

    if kinds:
        selected = [article for article in selected if article_kind(article) in kinds]
    if exclude_kinds:
        selected = [
            article for article in selected if article_kind(article) not in exclude_kinds
        ]

    return selected


def local_image_path(repo_root: Path, image: str) -> Path | None:
    if not image or image.startswith(("http://", "https://")):
        return None
    candidate = repo_root.joinpath(*image.lstrip("/").split("/"))
    if candidate.is_file():
        return candidate
    return None


def _open_image_bytes(data: bytes) -> Image.Image:
    image = Image.open(BytesIO(data))
    image.load()
    return image


def _download(url: str, timeout: float = 30.0) -> bytes:
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
        stream=True,
    )
    response.raise_for_status()
    return response.content


def _image_size_from_path(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size


def _image_size_from_bytes(data: bytes) -> tuple[int, int]:
    with _open_image_bytes(data) as image:
        return image.size


def ratio_needs_letterbox(width: int, height: int) -> bool:
    ratio = width / height
    return ratio < MIN_RATIO - 1e-9 or ratio > MAX_RATIO + 1e-9


def letterbox_image(
    source: Image.Image | Path | bytes,
    dest: Path,
    *,
    long_edge: int = LONG_EDGE,
    background: tuple[int, int, int] = (0, 0, 0),
) -> Path:
    """Pad image to the nearest allowed Instagram ratio; long edge = long_edge."""
    if isinstance(source, Path):
        image = Image.open(source)
        image.load()
    elif isinstance(source, bytes):
        image = _open_image_bytes(source)
    else:
        image = source

    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    elif image.mode == "L":
        image = image.convert("RGB")

    width, height = image.size
    ratio = width / height

    if ratio < MIN_RATIO:
        target_ratio = MIN_RATIO
    elif ratio > MAX_RATIO:
        target_ratio = MAX_RATIO
    else:
        target_ratio = ratio

    # Fit content into a canvas of target_ratio with long edge = long_edge.
    # Use ceil/floor so the final integer ratio stays inside [MIN_RATIO, MAX_RATIO].
    if target_ratio >= 1:
        canvas_w = long_edge
        canvas_h = max(1, math.ceil(long_edge / target_ratio))
        while canvas_w / canvas_h > MAX_RATIO:
            canvas_h += 1
    else:
        canvas_h = long_edge
        canvas_w = max(1, math.ceil(long_edge * target_ratio))
        while canvas_w / canvas_h < MIN_RATIO:
            canvas_w += 1

    scale = min(canvas_w / width, canvas_h / height)
    new_w = max(1, round(width * scale))
    new_h = max(1, round(height * scale))
    resized = image.resize((new_w, new_h), Image.Resampling.LANCZOS)

    canvas = Image.new("RGB", (canvas_w, canvas_h), background)
    offset = ((canvas_w - new_w) // 2, (canvas_h - new_h) // 2)
    canvas.paste(resized, offset)

    dest.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(dest, format="JPEG", quality=90, optimize=True)
    return dest


def resolve_image(
    article: Article,
    *,
    repo_root: Path,
    site_base: str,
    prepared_dir: Path,
) -> ImagePlan:
    notes: list[str] = []
    local = local_image_path(repo_root, article.image)
    public = absolute_url(article.image, site_base) if article.image else None

    width: int | None = None
    height: int | None = None
    source_bytes: bytes | None = None

    if local:
        notes.append(f"local file: {local}")
        width, height = _image_size_from_path(local)
    elif public and public.startswith(("http://", "https://")):
        notes.append(f"remote image: {public}")
        try:
            source_bytes = _download(public)
            width, height = _image_size_from_bytes(source_bytes)
            notes.append(f"downloaded for inspection ({width}x{height})")
        except Exception as exc:  # noqa: BLE001 — surface as note for dry-run
            notes.append(f"could not download remote image: {exc}")
    else:
        notes.append("no image field")

    needs = False
    letterboxed: Path | None = None
    if width and height:
        needs = ratio_needs_letterbox(width, height)
        notes.append(f"size {width}x{height}, ratio {width / height:.3f}")
        if needs:
            notes.append(
                f"outside Instagram range [{MIN_RATIO:.2f}, {MAX_RATIO:.2f}]; letterbox required"
            )
            dest = prepared_dir / f"{article.slug}.jpg"
            if local:
                letterbox_image(local, dest)
            elif source_bytes is not None:
                letterbox_image(source_bytes, dest)
            else:
                raise RuntimeError(
                    f"Cannot letterbox {article.slug}: image bytes unavailable"
                )
            letterboxed = dest
            notes.append(f"letterboxed JPEG: {dest}")
        else:
            notes.append("ratio OK for Instagram")
    else:
        notes.append("image dimensions unknown")

    return ImagePlan(
        local_path=local,
        public_url=public if public and public.startswith(("http://", "https://")) else None,
        width=width,
        height=height,
        needs_letterbox=needs,
        letterboxed_path=letterboxed,
        notes=notes,
    )


def public_url_reachable(url: str, timeout: float = 15.0) -> bool:
    try:
        response = requests.head(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            allow_redirects=True,
        )
        if response.status_code >= 400:
            # Some hosts reject HEAD; try a ranged GET.
            response = requests.get(
                url,
                headers={"User-Agent": USER_AGENT, "Range": "bytes=0-0"},
                timeout=timeout,
            )
        return response.status_code < 400
    except requests.RequestException:
        return False


def is_absolute_http(url: str | None) -> bool:
    if not url:
        return False
    return urlparse(url).scheme in ("http", "https")
