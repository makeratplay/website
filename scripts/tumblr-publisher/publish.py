#!/usr/bin/env python3
"""Publish Maker At Play project blog posts to Tumblr."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from parse_posts import (
    PROJECT_ANCHOR_RE,
    article_to_post,
    iter_publishable,
    load_project_posts,
    parse_blog_posts,
)
from tumblr_client import TumblrClient, TumblrConfig

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_ENV = SCRIPT_DIR / ".env"
MANIFEST_PATH = SCRIPT_DIR / "published.json"


def load_config(*, require_credentials: bool = True) -> TumblrConfig:
    load_dotenv(DEFAULT_ENV)
    client_id = os.getenv("TUMBLR_CLIENT_ID", "").strip()
    client_secret = os.getenv("TUMBLR_CLIENT_SECRET", "").strip()
    redirect_uri = os.getenv("TUMBLR_REDIRECT_URI", "http://127.0.0.1:8765/callback").strip()
    blog = os.getenv("TUMBLR_BLOG", "mlhblog.tumblr.com").strip()
    tags = [tag.strip() for tag in os.getenv("TUMBLR_TAGS", "marching band,props,2026,maker at play").split(",") if tag.strip()]
    project_dir = REPO_ROOT / os.getenv("PROJECT_DIR", "projects/64")

    if require_credentials:
        missing = []
        if not client_id:
            missing.append("TUMBLR_CLIENT_ID")
        if not client_secret:
            missing.append("TUMBLR_CLIENT_SECRET")
        if missing:
            raise SystemExit(
                "Missing required env vars: "
                + ", ".join(missing)
                + f"\nCopy {SCRIPT_DIR / 'config.example.env'} to {DEFAULT_ENV} and fill in values."
            )

    return TumblrConfig(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        blog=blog,
        tags=tags,
        project_dir=project_dir,
        token_path=SCRIPT_DIR / "token.json",
        source_url=os.getenv(
            "SOURCE_URL", "https://makeratplay.com/projects/64/index.html"
        ).strip(),
    )


def load_manifest() -> dict[str, dict]:
    if not MANIFEST_PATH.exists():
        return {}
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def save_manifest(manifest: dict[str, dict]) -> None:
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def cmd_auth(client: TumblrClient) -> None:
    client.authenticate()


def cmd_list(config: TumblrConfig, args: argparse.Namespace) -> None:
    posts = parse_blog_posts(REPO_ROOT / os.getenv("PROJECT_HTML", "projects/64/index.html"))
    manifest = load_manifest()
    publishable = list(iter_publishable(posts))

    print(f"Found {len(posts)} blog entries ({len(publishable)} publishable).\n")
    for post in posts:
        status = "placeholder" if post.is_placeholder else "ready"
        if post.date_key in manifest:
            status = f"published ({manifest[post.date_key]['id']})"
        marker = " *" if args.date and post.date_key == args.date else ""
        print(
            f"{post.date_key}  [{status}]  {post.title}  "
            f"(images={post.image_count}, video={'yes' if post.has_video else 'no'}){marker}"
        )


def _norm_text(value: str) -> str:
    text = (value or "").lower()
    text = text.replace("\u2013", "-").replace("\u2014", "-").replace("\u2019", "'")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _tumblr_text_rows(posts: list[dict]) -> list[str]:
    rows: list[str] = []
    for post in posts:
        first = ""
        for block in post.get("content") or []:
            if block.get("type") == "text" and block.get("text"):
                first = block["text"]
                break
        rows.append(_norm_text(first) + "\n" + _norm_text(post.get("summary") or ""))
    return rows


def _title_on_tumblr(title: str, rows: list[str]) -> bool:
    normalized = _norm_text(title)
    if not normalized:
        return False
    if len(normalized) < 12:
        pattern = re.compile(rf"(^|\s){re.escape(normalized)}(\s|$)")
        return any(pattern.search(row) for row in rows)
    return any(normalized in row for row in rows)


def _article_keys(article: dict) -> list[str]:
    keys = [article["slug"]]
    match = PROJECT_ANCHOR_RE.match(article.get("url", "").split("?")[0])
    if match:
        keys.append(match.group(2))
    return keys


def _tags_for_article(article: dict, post, config: TumblrConfig) -> list[str]:
    url = article.get("url", "")
    categories = [item.lower() for item in article.get("category") or []]
    topics = " ".join(article.get("topics") or []).lower()
    if url.startswith("/projects/") or "band props" in categories:
        tags = list(config.tags)
        if post.has_video and "Youtube" not in tags:
            tags.append("Youtube")
        return tags

    tags = ["makeratplay", "maker"]
    blob = " ".join(categories) + " " + topics + " " + url.lower()
    if "helper9" in blob:
        tags.append("helper9")
    if "model railroading" in blob:
        tags.append("modelrailroading")
    if "software" in topics or "ai" in topics:
        tags.append("software")
    if "healthcare" in topics:
        tags.append("healthcare")
    if "career" in topics or "leadership" in topics or "cto" in blob:
        tags.append("leadership")
    if "workbench" in categories:
        tags.append("workbench")
    if "making" in topics:
        tags.append("making")
    if post.has_video and "Youtube" not in tags:
        tags.append("Youtube")
    return tags


def _select_articles(config: TumblrConfig, client: TumblrClient, args: argparse.Namespace):
    articles_path = Path(args.articles)
    if not articles_path.is_absolute():
        articles_path = REPO_ROOT / articles_path
    articles = json.loads(articles_path.read_text(encoding="utf-8"))
    manifest = load_manifest()

    selected_articles = []
    for article in articles:
        article_date = str(article.get("date") or "")
        if args.date and article_date != args.date:
            continue
        if args.from_date and article_date < args.from_date:
            continue
        if args.to_date and article_date > args.to_date:
            continue
        selected_articles.append(article)

    print(f"Checking {config.blog} for posts that are already published ...")
    tumblr_rows = _tumblr_text_rows(client.list_posts())
    skipped = 0
    pending = []
    for article in selected_articles:
        if any(key in manifest for key in _article_keys(article)) or _title_on_tumblr(article["title"], tumblr_rows):
            skipped += 1
            continue
        pending.append(article)

    project_posts = load_project_posts(REPO_ROOT, pending)
    posts = []
    seen_projects: set[str] = set()
    for article in pending:
        post = article_to_post(article, REPO_ROOT, project_posts)
        if post is None:
            print(f"  SKIP: no publishable content for {article['slug']}")
            continue
        if post.manifest_key in seen_projects:
            continue
        seen_projects.add(post.manifest_key or post.date_key)
        post.tags = _tags_for_article(article, post, config)
        posts.append(post)

    posts.sort(key=lambda post: (post.post_date, post.slug or post.title))
    print(f"Articles in range: {len(selected_articles)}. Already on Tumblr: {skipped}. To publish: {len(posts)}.")
    return posts, manifest


def cmd_publish(config: TumblrConfig, client: TumblrClient, args: argparse.Namespace) -> None:
    if args.articles:
        selected, manifest = _select_articles(config, client, args)
    else:
        html_path = REPO_ROOT / os.getenv("PROJECT_HTML", "projects/64/index.html")
        posts = parse_blog_posts(html_path)
        manifest = load_manifest()
        selected = list(iter_publishable(posts))

        if args.date:
            selected = [post for post in selected if post.date_key == args.date]
            if not selected:
                raise SystemExit(f"No publishable post found for date {args.date}")

        if args.from_date:
            selected = [post for post in selected if post.post_date.isoformat() >= args.from_date]
        if args.to_date:
            selected = [post for post in selected if post.post_date.isoformat() <= args.to_date]

        if args.skip_published:
            selected = [post for post in selected if post.date_key not in manifest]

    if not selected:
        print("Nothing to publish.")
        return

    if args.newest_first:
        selected = list(reversed(selected))

    print(f"{'Dry run' if args.dry_run else 'Publishing'} {len(selected)} post(s) to {config.blog} ...")
    for index, post in enumerate(selected, start=1):
        print(f"\n[{index}/{len(selected)}] {post.date_key} — {post.title}")
        try:
            result = client.create_post(
                post,
                state=args.state,
                dry_run=args.dry_run,
            )
        except FileNotFoundError as exc:
            print(f"  SKIP: {exc}")
            if args.stop_on_error:
                raise SystemExit(1) from exc
            continue
        except RuntimeError as exc:
            print(f"  ERROR: {exc}")
            if args.stop_on_error:
                raise SystemExit(1) from exc
            continue

        if args.dry_run:
            tag_note = f", tags={', '.join(post.tags)}" if post.tags else ""
            print(f"  blocks={result['blocks']}, uploads={result['uploads']}{tag_note}")
            continue

        manifest_key = post.manifest_key or post.date_key
        entry = {
            "id": result["id"],
            "title": post.title,
            "state": args.state,
        }
        if post.slug:
            entry["slug"] = post.slug
        manifest[manifest_key] = entry
        save_manifest(manifest)
        print(f"  Created Tumblr post id={result['id']}")

        if args.delay and index < len(selected):
            time.sleep(args.delay)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish project blog posts to Tumblr.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("auth", help="Authenticate with Tumblr OAuth2")

    list_parser = subparsers.add_parser("list", help="List blog posts found in index.html")
    list_parser.add_argument("--date", help="Highlight a specific YYYY-MM-DD date")

    publish_parser = subparsers.add_parser("publish", help="Publish posts to Tumblr")
    publish_parser.add_argument("--date", help="Publish one post by YYYY-MM-DD")
    publish_parser.add_argument(
        "--articles",
        nargs="?",
        const="content/articles.json",
        help="Publish entries from articles.json (path optional; default content/articles.json)",
    )
    publish_parser.add_argument("--from-date", help="Publish posts on/after YYYY-MM-DD")
    publish_parser.add_argument("--to-date", help="Publish posts on/before YYYY-MM-DD")
    publish_parser.add_argument(
        "--state",
        default="published",
        choices=["published", "draft", "queue", "private"],
        help="Initial Tumblr post state (default: published)",
    )
    publish_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build payloads without calling Tumblr",
    )
    publish_parser.add_argument(
        "--skip-published",
        action="store_true",
        help="Skip dates already recorded in published.json",
    )
    publish_parser.add_argument(
        "--newest-first",
        action="store_true",
        help="Publish newest posts first (default: oldest first)",
    )
    publish_parser.add_argument(
        "--delay",
        type=float,
        default=3.0,
        help="Seconds to wait between posts (default: 3)",
    )
    publish_parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop immediately if a post fails",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "list":
        config = load_config(require_credentials=False)
        cmd_list(config, args)
        return

    config = load_config()
    client = TumblrClient(config)

    if args.command == "auth":
        cmd_auth(client)
    elif args.command == "publish":
        cmd_publish(config, client, args)
    else:
        parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
