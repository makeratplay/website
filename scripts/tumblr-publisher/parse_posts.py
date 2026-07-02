"""Parse progress blog posts from a Maker At Play project index.html file."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Iterator

from bs4 import BeautifulSoup, NavigableString, Tag


DATE_HEADING_RE = re.compile(
    r"^(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+"
    r"([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})$"
)
YOUTUBE_EMBED_RE = re.compile(
    r"(?:youtube\.com/embed/|youtube\.com/watch\?v=|youtu\.be/)([A-Za-z0-9_-]{11})"
)
PLACEHOLDER_RE = re.compile(r"write-up coming soon", re.I)


@dataclass
class TextBlock:
    text: str
    subtype: str | None = None
    formatting: list[dict] | None = None
    is_title: bool = False


@dataclass
class ImageBlock:
    filename: str
    alt: str = ""


@dataclass
class VideoBlock:
    youtube_id: str
    url: str


ContentBlock = TextBlock | ImageBlock | VideoBlock


@dataclass
class BlogPost:
    display_date: str
    post_date: date
    title: str
    blocks: list[ContentBlock] = field(default_factory=list)

    @property
    def date_key(self) -> str:
        return self.post_date.isoformat()

    @property
    def is_placeholder(self) -> bool:
        content_blocks = [
            block
            for block in self.blocks
            if not (isinstance(block, TextBlock) and block.is_title)
        ]
        if not content_blocks:
            return True
        if len(content_blocks) == 1 and isinstance(content_blocks[0], TextBlock):
            return bool(PLACEHOLDER_RE.search(content_blocks[0].text or ""))
        return False

    @property
    def image_count(self) -> int:
        return sum(1 for b in self.blocks if isinstance(b, ImageBlock))

    @property
    def has_video(self) -> bool:
        return any(isinstance(b, VideoBlock) for b in self.blocks)


def _parse_heading_date(text: str) -> date:
    match = DATE_HEADING_RE.match(text.strip())
    if not match:
        raise ValueError(f"Could not parse blog post date from heading: {text!r}")
    month_name, day, year = match.groups()
    parsed = datetime.strptime(f"{month_name} {day} {year}", "%B %d %Y")
    return parsed.date()


def _element_text(element: Tag) -> str:
    return " ".join(element.stripped_strings)


def _normalize_inline_text(text: str) -> str:
    """Collapse HTML source line breaks and whitespace within a single block."""
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _inline_formatting(element: Tag) -> tuple[str, list[dict] | None]:
    """Convert paragraph inline markup to NPF text + formatting ranges."""
    text = _normalize_inline_text(element.get_text())
    if not text:
        return "", None

    formatting: list[dict] = []
    seen: set[tuple[str, int, int]] = set()

    def add_formatting(fmt_type: str, snippet: str) -> None:
        snippet = _normalize_inline_text(snippet)
        if not snippet:
            return
        start = 0
        while True:
            index = text.find(snippet, start)
            if index < 0:
                break
            key = (fmt_type, index, index + len(snippet))
            if key not in seen:
                seen.add(key)
                formatting.append(
                    {"type": fmt_type, "start": index, "end": index + len(snippet)}
                )
            start = index + len(snippet)

    for node in element.find_all(["strong", "b"]):
        add_formatting("bold", node.get_text())
    for node in element.find_all(["em", "i"]):
        add_formatting("italic", node.get_text())

    formatting.sort(key=lambda item: item["start"])
    return text, formatting or None


def _extract_youtube(div: Tag) -> VideoBlock | None:
    iframe = div.find("iframe", src=True)
    if iframe:
        match = YOUTUBE_EMBED_RE.search(iframe["src"])
        if match:
            video_id = match.group(1)
            return VideoBlock(
                youtube_id=video_id,
                url=f"https://www.youtube.com/watch?v={video_id}",
            )

    for anchor in div.find_all("a", href=True):
        match = YOUTUBE_EMBED_RE.search(anchor["href"])
        if match:
            video_id = match.group(1)
            return VideoBlock(
                youtube_id=video_id,
                url=f"https://www.youtube.com/watch?v={video_id}",
            )
    return None


def _extract_images(div: Tag) -> list[ImageBlock]:
    images: list[ImageBlock] = []
    seen: set[str] = set()
    for img in div.find_all("img", src=True):
        filename = Path(img["src"]).name
        if filename in seen:
            continue
        seen.add(filename)
        images.append(ImageBlock(filename=filename, alt=img.get("alt", "")))
    return images


def _parse_body(body: Tag) -> list[ContentBlock]:
    blocks: list[ContentBlock] = []

    for child in body.children:
        if not isinstance(child, Tag):
            continue

        if child.name == "h5":
            title = _element_text(child)
            if title:
                blocks.append(
                    TextBlock(
                        text=title,
                        is_title=True,
                        formatting=[{"type": "bold", "start": 0, "end": len(title)}],
                    )
                )
            continue

        if child.name == "p":
            if "text-center" in child.get("class", []):
                continue
            text, formatting = _inline_formatting(child)
            if text:
                blocks.append(TextBlock(text=text, formatting=formatting))
            continue

        if child.name == "ul":
            for item in child.find_all("li", recursive=False):
                text, formatting = _inline_formatting(item)
                if text:
                    blocks.append(
                        TextBlock(
                            text=text,
                            subtype="unordered-list-item",
                            formatting=formatting,
                        )
                    )
            continue

        if child.name == "div":
            classes = child.get("class", [])
            class_str = " ".join(classes)
            if "blog-post-video" in classes:
                video = _extract_youtube(child)
                if video:
                    blocks.append(video)
                continue
            if "blog-post-images" in classes or "blog-post-image" in class_str:
                blocks.extend(_extract_images(child))
                continue

    return blocks


def parse_blog_posts(html_path: Path) -> list[BlogPost]:
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
    posts: list[BlogPost] = []

    for article in soup.select("div.blog-post"):
        heading = article.find("h4")
        body = article.find("div", class_="blog-post-body")
        if not heading or not body:
            continue

        display_date = _element_text(heading)
        post_date = _parse_heading_date(display_date)
        title_tag = body.find("h5")
        title = _element_text(title_tag) if title_tag else display_date
        blocks = _parse_body(body)

        posts.append(
            BlogPost(
                display_date=display_date,
                post_date=post_date,
                title=title,
                blocks=blocks,
            )
        )

    posts.sort(key=lambda post: post.post_date)
    return posts


def iter_publishable(posts: Iterable[BlogPost]) -> Iterator[BlogPost]:
    for post in posts:
        if not post.is_placeholder and post.blocks:
            yield post
