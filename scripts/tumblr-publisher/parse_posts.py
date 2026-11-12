"""Parse progress blog posts from a Maker At Play project index.html file."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Iterator
from urllib.parse import quote, urlparse, urlsplit, urlunsplit

from bs4 import BeautifulSoup, NavigableString, Tag

SITE_BASE = "https://makeratplay.com"
PROJECT_ANCHOR_RE = re.compile(r"^(/projects/\d+/index\.html)#blog-(\d{4}-\d{2}-\d{2})$")
MAX_IMAGES = 20


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
    path: Path | None = None
    url: str | None = None
    priority: int = 0


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
    source_url: str | None = None
    tags: list[str] | None = None
    manifest_key: str | None = None
    slug: str | None = None

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


def site_url(url: str) -> str:
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if not url.startswith("/"):
        url = "/" + url
    return SITE_BASE + url


def _encode_url(href: str) -> str:
    if href.startswith("mailto:"):
        return href
    parts = urlsplit(href)
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            quote(parts.path, safe="/%"),
            quote(parts.query, safe="=&%?+/"),
            quote(parts.fragment, safe="%"),
        )
    )


def _abs_href(href: str) -> str:
    href = (href or "").strip()
    if not href or href.startswith(("#", "javascript:")):
        return ""
    if href.startswith("//"):
        href = "https:" + href
    elif href.startswith("/"):
        href = SITE_BASE + href
    elif not href.startswith(("http://", "https://", "mailto:")):
        return ""
    return _encode_url(href)


def _render_inline(element: Tag) -> tuple[str, list[dict] | None]:
    """Convert inline markup to NPF text plus formatting ranges."""
    chars: list[tuple[str, tuple[tuple[str, str | None], ...]]] = []

    def walk(node, formats: tuple[tuple[str, str | None], ...]) -> None:
        if isinstance(node, NavigableString):
            for char in str(node).replace("\xa0", " "):
                chars.append((char, formats))
            return
        if not isinstance(node, Tag):
            return
        if node.name == "br":
            chars.append((" ", formats))
            return
        if node.name == "img":
            return
        next_formats = formats
        if node.name in {"strong", "b"}:
            next_formats = formats + (("bold", None),)
        elif node.name in {"em", "i"}:
            next_formats = formats + (("italic", None),)
        elif node.name == "a" and node.get("href") and node.find("img") is None:
            href = _abs_href(node["href"])
            if href:
                next_formats = formats + (("link", href),)
        for child in node.children:
            walk(child, next_formats)

    for child in element.children:
        walk(child, ())

    collapsed: list[tuple[str, tuple[tuple[str, str | None], ...]]] = []
    previous_space = True
    for char, formats in chars:
        if char.isspace():
            if previous_space:
                continue
            collapsed.append((" ", formats))
            previous_space = True
            continue
        collapsed.append((char, formats))
        previous_space = False
    while collapsed and collapsed[-1][0] == " ":
        collapsed.pop()
    if not collapsed:
        return "", None

    text = "".join(char for char, _ in collapsed)
    formatting: list[dict] = []
    index = 0
    while index < len(collapsed):
        formats = collapsed[index][1]
        end = index + 1
        while end < len(collapsed) and collapsed[end][1] == formats:
            end += 1
        seen: set[tuple[str, str | None]] = set()
        for fmt_type, url in formats:
            key = (fmt_type, url)
            if key in seen:
                continue
            seen.add(key)
            item = {"type": fmt_type, "start": index, "end": end}
            if url:
                item["url"] = url
            formatting.append(item)
        index = end
    return text, formatting or None


def _image_from_src(src: str, alt: str, page_dir: Path, repo_root: Path, priority: int = 0) -> ImageBlock:
    filename = Path(urlparse(src).path).name or "image"
    if src.startswith(("http://", "https://")):
        return ImageBlock(filename=filename, alt=alt, url=src, priority=priority)
    if src.startswith("/"):
        path = repo_root / src.lstrip("/")
        return ImageBlock(filename=filename, alt=alt, path=path, priority=priority)
    path = (page_dir / src).resolve()
    return ImageBlock(filename=path.name, alt=alt, path=path, priority=priority)


def _image_key(block: ImageBlock) -> str:
    if block.path is not None:
        return str(block.path).lower()
    if block.url:
        return block.url
    return block.filename.lower()


def _append_image(blocks: list[ContentBlock], image: ImageBlock) -> None:
    seen = {_image_key(block) for block in blocks if isinstance(block, ImageBlock)}
    if _image_key(image) in seen:
        return
    blocks.append(image)


def _is_caption(block: ContentBlock) -> bool:
    return (
        isinstance(block, TextBlock)
        and bool(block.formatting)
        and any(item.get("type") == "italic" and item.get("start") == 0 for item in block.formatting)
    )


def _cap_images(blocks: list[ContentBlock], limit: int = MAX_IMAGES) -> list[ContentBlock]:
    image_indexes = [index for index, block in enumerate(blocks) if isinstance(block, ImageBlock)]
    if len(image_indexes) <= limit:
        return blocks
    remove: set[int] = set()
    for index in image_indexes:
        if len(image_indexes) - len(remove) <= limit:
            break
        block = blocks[index]
        if isinstance(block, ImageBlock) and block.priority < 0:
            remove.add(index)
    if len(image_indexes) - len(remove) > limit:
        kept = [index for index in image_indexes if index not in remove]
        overflow = len(kept) - limit
        remove.update(kept[:overflow])
    for index in list(remove):
        if index + 1 < len(blocks) and _is_caption(blocks[index + 1]):
            remove.add(index + 1)
    return [block for index, block in enumerate(blocks) if index not in remove]


def _is_back_link(text: str) -> bool:
    lowered = text.lstrip().lower()
    return lowered.startswith("←") or lowered.startswith("back to ")


def _consume_editorial(node: Tag, blocks: list[ContentBlock], page_dir: Path, repo_root: Path) -> None:
    if not isinstance(node, Tag):
        return
    if node.name in {"script", "style", "footer"}:
        return

    if node.name == "figure":
        for img in node.find_all("img", src=True):
            classes = img.get("class", [])
            priority = -1 if "editorial-thumb" in classes else 0
            _append_image(
                blocks,
                _image_from_src(img["src"], img.get("alt", ""), page_dir, repo_root, priority),
            )
        caption = node.find("figcaption")
        if caption:
            text, formatting = _render_inline(caption)
            if text:
                italic = {"type": "italic", "start": 0, "end": len(text)}
                blocks.append(TextBlock(text=text, formatting=[italic, *(formatting or [])]))
        return

    if node.name == "img" and node.get("src"):
        classes = node.get("class", [])
        priority = -1 if "editorial-thumb" in classes else 0
        _append_image(
            blocks,
            _image_from_src(node["src"], node.get("alt", ""), page_dir, repo_root, priority),
        )
        return

    if node.name in {"h2", "h3", "h4", "h5", "h6"}:
        text, formatting = _render_inline(node)
        if not text:
            return
        if node.name == "h2":
            blocks.append(TextBlock(text=text, subtype="heading2", formatting=formatting))
        else:
            bold = {"type": "bold", "start": 0, "end": len(text)}
            blocks.append(TextBlock(text=text, formatting=[bold, *(formatting or [])]))
        return

    if node.name == "blockquote":
        paragraphs = node.find_all("p") or [node]
        for paragraph in paragraphs:
            text, formatting = _render_inline(paragraph)
            if text:
                blocks.append(TextBlock(text=text, subtype="quote", formatting=formatting))
        return

    if node.name in {"ul", "ol"}:
        subtype = "unordered-list-item" if node.name == "ul" else "ordered-list-item"
        for item in node.find_all("li", recursive=False):
            text, formatting = _render_inline(item)
            if text:
                blocks.append(TextBlock(text=text, subtype=subtype, formatting=formatting))
        return

    if node.name == "p":
        text, formatting = _render_inline(node)
        if text and not _is_back_link(text):
            blocks.append(TextBlock(text=text, formatting=formatting))
        return

    video = _extract_youtube(node) if node.name in {"iframe", "div"} else None
    if video and node.name == "iframe":
        blocks.append(video)
        return
    if video and node.name == "div" and "blog-post-video" in node.get("class", []):
        blocks.append(video)
        return

    if node.name == "a":
        if node.find("img") is None:
            text, formatting = _render_inline(node)
            if text and not _is_back_link(text):
                blocks.append(TextBlock(text=text, formatting=formatting))
            return
        for child in node.children:
            if isinstance(child, Tag):
                _consume_editorial(child, blocks, page_dir, repo_root)
        return

    if node.name in {"div", "article", "section", "main"}:
        for child in node.children:
            if isinstance(child, Tag):
                _consume_editorial(child, blocks, page_dir, repo_root)


def _title_block(title: str) -> TextBlock:
    return TextBlock(
        text=title,
        is_title=True,
        formatting=[{"type": "bold", "start": 0, "end": len(title)}],
    )


def _ensure_hero(
    blocks: list[ContentBlock],
    article: dict,
    page_dir: Path,
    repo_root: Path,
) -> list[ContentBlock]:
    src = (article.get("image") or "").strip()
    if not src:
        return blocks
    hero = _image_from_src(src, article.get("title", ""), page_dir, repo_root)
    if any(isinstance(block, ImageBlock) and _image_key(block) == _image_key(hero) for block in blocks):
        return blocks
    if blocks and isinstance(blocks[0], TextBlock) and blocks[0].is_title:
        return [blocks[0], hero, *blocks[1:]]
    return [hero, *blocks]


def _local_article_html(repo_root: Path, url: str) -> Path | None:
    if not url.startswith("/") or url.startswith("/projects/"):
        return None
    relative = url.split("#", 1)[0].strip("/")
    candidate = repo_root / relative / "index.html"
    if candidate.is_file():
        return candidate
    direct = repo_root / relative
    if direct.is_file():
        return direct
    return None


def _read_more_label(url: str) -> str:
    lowered = url.lower()
    if "helper9.ai" in lowered:
        return "Read on Helper9"
    if "linkedin.com" in lowered or "lnkd.in" in lowered:
        return "Read on LinkedIn"
    return "Read the full article"


def _external_article_post(article: dict, repo_root: Path) -> BlogPost:
    title = article["title"]
    blocks: list[ContentBlock] = [_title_block(title)]
    summary = (article.get("summary") or "").strip()
    if summary:
        blocks.append(TextBlock(text=summary))
    page_dir = repo_root
    blocks = _ensure_hero(blocks, article, page_dir, repo_root)
    url = site_url(article["url"])
    label = _read_more_label(url)
    blocks.append(
        TextBlock(
            text=label,
            formatting=[{"type": "link", "start": 0, "end": len(label), "url": url}],
        )
    )
    post_date = date.fromisoformat(article["date"])
    return BlogPost(
        display_date=article["date"],
        post_date=post_date,
        title=title,
        blocks=_cap_images(blocks),
        source_url=url,
        manifest_key=article["slug"],
        slug=article["slug"],
    )


def _editorial_article_post(article: dict, html_path: Path, repo_root: Path) -> BlogPost:
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
    root = soup.select_one("div.editorial-article") or soup.select_one("main") or soup.body
    blocks: list[ContentBlock] = [_title_block(article["title"])]
    if root is not None:
        _consume_editorial(root, blocks, html_path.parent, repo_root)
    blocks = _ensure_hero(blocks, article, html_path.parent, repo_root)
    image_count = sum(isinstance(block, ImageBlock) for block in blocks)
    blocks = _cap_images(blocks)
    if sum(isinstance(block, ImageBlock) for block in blocks) < image_count:
        note = "More photos are in the full article."
        blocks.append(
            TextBlock(
                text=note,
                formatting=[{"type": "link", "start": 0, "end": len(note), "url": site_url(article["url"])}],
            )
        )
    post_date = date.fromisoformat(article["date"])
    return BlogPost(
        display_date=article["date"],
        post_date=post_date,
        title=article["title"],
        blocks=blocks,
        source_url=site_url(article["url"]),
        manifest_key=article["slug"],
        slug=article["slug"],
    )


def load_project_posts(repo_root: Path, articles: list[dict]) -> dict[tuple[str, str], BlogPost]:
    paths: set[str] = set()
    for article in articles:
        match = PROJECT_ANCHOR_RE.match(article.get("url", "").split("?")[0])
        if match:
            paths.add(match.group(1))
    found: dict[tuple[str, str], BlogPost] = {}
    for relative in sorted(paths):
        for post in parse_blog_posts(repo_root / relative.lstrip("/")):
            found[(relative, post.date_key)] = post
    return found


def article_to_post(
    article: dict,
    repo_root: Path,
    project_posts: dict[tuple[str, str], BlogPost],
) -> BlogPost | None:
    url = article.get("url", "").split("?")[0]
    match = PROJECT_ANCHOR_RE.match(url)
    if match:
        post = project_posts.get((match.group(1), match.group(2)))
        if post is None or post.is_placeholder:
            return None
        post.slug = article["slug"]
        post.manifest_key = post.date_key
        return post

    local_html = _local_article_html(repo_root, url)
    if local_html is not None:
        return _editorial_article_post(article, local_html, repo_root)
    return _external_article_post(article, repo_root)
