#!/usr/bin/env python3
"""Publish Maker At Play articles to Facebook and Instagram."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from articles import (
    Article,
    ImagePlan,
    absolute_url,
    build_caption,
    is_absolute_http,
    load_articles,
    public_url_reachable,
    resolve_image,
    select_articles,
)
from meta_client import MetaClient, MetaConfig

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_ENV = SCRIPT_DIR / ".env"
MANIFEST_PATH = SCRIPT_DIR / "published.json"
DEFAULT_ARTICLES = REPO_ROOT / "content" / "articles.json"


def load_config(*, require_credentials: bool = True) -> MetaConfig:
    load_dotenv(DEFAULT_ENV)
    app_id = os.getenv("META_APP_ID", "").strip()
    app_secret = os.getenv("META_APP_SECRET", "").strip()
    page_id = os.getenv("META_PAGE_ID", "makeratplay").strip()
    site_base = os.getenv("SITE_BASE_URL", "https://makeratplay.com").strip().rstrip("/")
    hashtags = [
        tag.strip()
        for tag in os.getenv("META_HASHTAGS", "#MakerAtPlay #Making").replace(",", " ").split()
        if tag.strip()
    ]
    graph_version = os.getenv("META_GRAPH_VERSION", "v21.0").strip()
    articles_path = Path(os.getenv("ARTICLES_PATH", str(DEFAULT_ARTICLES)))
    if not articles_path.is_absolute():
        articles_path = REPO_ROOT / articles_path

    if require_credentials:
        missing = []
        if not app_id:
            missing.append("META_APP_ID")
        if not app_secret:
            missing.append("META_APP_SECRET")
        if missing:
            raise SystemExit(
                "Missing required env vars: "
                + ", ".join(missing)
                + f"\nCopy {SCRIPT_DIR / 'config.example.env'} to {DEFAULT_ENV} and fill in values."
            )

    return MetaConfig(
        app_id=app_id,
        app_secret=app_secret,
        page_id=page_id,
        site_base_url=site_base,
        hashtags=hashtags,
        graph_version=graph_version,
        token_path=SCRIPT_DIR / "token.json",
        articles_path=articles_path,
        prepared_dir=SCRIPT_DIR / "prepared",
        repo_root=REPO_ROOT,
    )


def load_manifest() -> dict[str, dict[str, Any]]:
    if not MANIFEST_PATH.exists():
        return {}
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def save_manifest(manifest: dict[str, dict[str, Any]]) -> None:
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def platform_status(entry: dict[str, Any] | None, platform: str) -> str:
    if not entry:
        return "ready"
    value = entry.get(platform)
    if isinstance(value, dict) and value.get("id"):
        return f"published ({value['id']})"
    if isinstance(value, str) and value:
        return f"published ({value})"
    return "ready"


def already_published(entry: dict[str, Any] | None, platform: str) -> bool:
    if not entry:
        return False
    value = entry.get(platform)
    if isinstance(value, dict):
        return bool(value.get("id"))
    return bool(value)


def platforms_done_for(entry: dict[str, Any] | None, platform: str) -> bool:
    """True when every requested platform already has a recorded post id."""
    if platform == "facebook":
        return already_published(entry, "facebook")
    if platform == "instagram":
        return already_published(entry, "instagram")
    return already_published(entry, "facebook") and already_published(entry, "instagram")


def recorded_ids_summary(entry: dict[str, Any] | None) -> str:
    if not entry:
        return "none"
    parts: list[str] = []
    for name in ("facebook", "instagram"):
        value = entry.get(name)
        if isinstance(value, dict) and value.get("id"):
            parts.append(f"{name}={value['id']}")
        elif isinstance(value, str) and value:
            parts.append(f"{name}={value}")
    return ", ".join(parts) if parts else "none"


def cmd_auth(client: MetaClient, args: argparse.Namespace) -> None:
    client.authenticate(args.token)


def cmd_list(config: MetaConfig, args: argparse.Namespace) -> None:
    articles = load_articles(config.articles_path)
    if args.slug or args.date or args.from_date or args.to_date:
        articles = select_articles(
            articles,
            slug=args.slug,
            date=args.date,
            from_date=args.from_date,
            to_date=args.to_date,
        )
    manifest = load_manifest()

    print(f"Found {len(articles)} article(s) in {config.articles_path.name}.\n")
    for article in articles:
        entry = manifest.get(article.slug)
        fb = platform_status(entry, "facebook")
        ig = platform_status(entry, "instagram")
        marker = " *" if args.slug and article.slug == args.slug else ""
        print(
            f"{article.date}  {article.slug}{marker}\n"
            f"  title: {article.title}\n"
            f"  facebook: {fb}\n"
            f"  instagram: {ig}\n"
        )


def _facebook_image_args(plan: ImagePlan) -> tuple[Path | None, str | None]:
    if plan.needs_letterbox and plan.letterboxed_path:
        return plan.letterboxed_path, None
    if plan.local_path:
        return plan.local_path, None
    if plan.public_url:
        return None, plan.public_url
    raise RuntimeError("No image available for Facebook")


def _instagram_image_url(
    client: MetaClient,
    plan: ImagePlan,
    *,
    facebook_photo_id: str | None,
    dry_run: bool,
    allow_fb_staging: bool,
) -> tuple[str, str | None]:
    """Return (image_url, staging_photo_id_or_none)."""
    if plan.needs_letterbox:
        if dry_run:
            return (
                f"(letterboxed via Facebook CDN after upload: {plan.letterboxed_path})",
                None,
            )
        if facebook_photo_id:
            return client.facebook_photo_cdn_url(facebook_photo_id), None
        if not allow_fb_staging:
            raise RuntimeError(
                "Instagram needs a letterboxed image hosted at a public URL. "
                "Post with --platform both (or facebook first), or ensure SITE_BASE_URL "
                "serves a ratio-valid image."
            )
        # Stage unpublished photo on the Page to obtain a CDN URL.
        if not plan.letterboxed_path:
            raise RuntimeError("Letterboxed image missing")
        staged = client.create_facebook_photo(
            caption="",
            image_path=plan.letterboxed_path,
            published=False,
            dry_run=False,
        )
        staged_id = staged["id"]
        return client.facebook_photo_cdn_url(staged_id), staged_id

    # Ratio OK — prefer public URL Instagram can fetch.
    if plan.public_url and is_absolute_http(plan.public_url):
        if dry_run:
            reachable = public_url_reachable(plan.public_url)
            note = "reachable" if reachable else "NOT reachable yet"
            return f"{plan.public_url} ({note})", None
        if public_url_reachable(plan.public_url):
            return plan.public_url, None
        if facebook_photo_id:
            return client.facebook_photo_cdn_url(facebook_photo_id), None
        raise RuntimeError(
            f"Instagram image URL is not publicly reachable: {plan.public_url}. "
            "Deploy the site asset first, or publish Facebook first so a CDN URL is available."
        )

    if facebook_photo_id and not dry_run:
        return client.facebook_photo_cdn_url(facebook_photo_id), None

    if dry_run and plan.local_path:
        return (
            f"(local only: {plan.local_path}; needs public URL or Facebook CDN)",
            None,
        )

    raise RuntimeError(
        "Instagram requires a public image URL. No absolute image URL is available, "
        "and no Facebook photo CDN URL was produced."
    )


def record_platform(
    manifest: dict[str, dict[str, Any]],
    article: Article,
    platform: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Persist a platform post id under the article slug immediately after success."""
    entry = dict(manifest.get(article.slug) or {})
    entry["title"] = article.title
    entry["date"] = article.date
    entry[platform] = payload
    manifest[article.slug] = entry
    save_manifest(manifest)
    return entry


def publish_one(
    config: MetaConfig,
    client: MetaClient | None,
    article: Article,
    *,
    platform: str,
    dry_run: bool,
    force: bool,
    manifest: dict[str, dict[str, Any]],
) -> None:
    caption = build_caption(article, config.site_base_url, config.hashtags)
    plan = resolve_image(
        article,
        repo_root=config.repo_root,
        site_base=config.site_base_url,
        prepared_dir=config.prepared_dir,
    )
    article_url = absolute_url(article.url, config.site_base_url)
    entry = dict(manifest.get(article.slug) or {})
    entry.setdefault("title", article.title)
    entry.setdefault("date", article.date)

    want_fb = platform in ("facebook", "both")
    want_ig = platform in ("instagram", "both")
    # Always skip platforms that already have an id unless --force.
    skip_fb = want_fb and already_published(entry, "facebook") and not force
    skip_ig = want_ig and already_published(entry, "instagram") and not force

    print(f"  url: {article_url}")
    print(f"  caption ({len(caption)} chars):")
    for line in caption.strip().splitlines():
        print(f"    {line}")
    for note in plan.notes:
        print(f"  image: {note}")

    if dry_run:
        if want_fb and not skip_fb:
            fb_path, fb_url = _facebook_image_args(plan)
            print(f"  facebook: would post photo path={fb_path} url={fb_url}")
        elif skip_fb:
            print(f"  facebook: already published ({recorded_ids_summary({'facebook': entry.get('facebook')})}), skip")
        if want_ig and not skip_ig:
            ig_url, _ = _instagram_image_url(
                client or MetaClient(config),
                plan,
                facebook_photo_id=None,
                dry_run=True,
                allow_fb_staging=platform == "instagram",
            )
            print(f"  instagram: would post image_url={ig_url}")
        elif skip_ig:
            print(f"  instagram: already published ({recorded_ids_summary({'instagram': entry.get('instagram')})}), skip")
        return

    assert client is not None

    facebook_photo_id: str | None = None
    if already_published(entry, "facebook"):
        existing = entry["facebook"]
        facebook_photo_id = existing.get("id") if isinstance(existing, dict) else str(existing)

    if want_fb and not skip_fb:
        fb_path, fb_url = _facebook_image_args(plan)
        result = client.create_facebook_photo(
            caption=caption,
            image_path=fb_path,
            image_url=fb_url,
            published=True,
            dry_run=False,
        )
        facebook_photo_id = result["id"]
        fb_record: dict[str, Any] = {
            "id": facebook_photo_id,
            "published": True,
        }
        if result.get("post_id"):
            fb_record["post_id"] = result["post_id"]
        entry = record_platform(manifest, article, "facebook", fb_record)
        print(f"  facebook: created photo id={facebook_photo_id}")
    elif skip_fb:
        print(f"  facebook: already published ({facebook_photo_id}), skip")

    if want_ig and not skip_ig:
        ig_url, staged_id = _instagram_image_url(
            client,
            plan,
            facebook_photo_id=facebook_photo_id,
            dry_run=False,
            allow_fb_staging=platform == "instagram" or not want_fb,
        )
        if staged_id:
            entry = record_platform(
                manifest,
                article,
                "facebook_staging",
                {"id": staged_id, "published": False},
            )
            print(f"  facebook staging (unpublished): id={staged_id}")

        result = client.create_instagram_media(
            caption=caption,
            image_url=ig_url,
            dry_run=False,
        )
        entry = record_platform(
            manifest,
            article,
            "instagram",
            {
                "id": result["id"],
                "container_id": result.get("container_id"),
            },
        )
        print(f"  instagram: published media id={result['id']}")
    elif skip_ig:
        existing_ig = entry.get("instagram")
        ig_id = (
            existing_ig.get("id")
            if isinstance(existing_ig, dict)
            else existing_ig
        )
        print(f"  instagram: already published ({ig_id}), skip")


def cmd_publish(config: MetaConfig, client: MetaClient | None, args: argparse.Namespace) -> None:
    if not (args.slug or args.date or args.from_date or args.to_date):
        raise SystemExit(
            "Refuse to publish the whole catalog. Pass --slug, --date, --from-date, and/or --to-date."
        )

    articles = select_articles(
        load_articles(config.articles_path),
        slug=args.slug,
        date=args.date,
        from_date=args.from_date,
        to_date=args.to_date,
    )
    manifest = load_manifest()
    force = bool(getattr(args, "force", False))

    # Default: never create duplicates. Filter out slugs already recorded for
    # the requested platform(s). --force republishes anyway.
    if not force:
        remaining: list[Article] = []
        skipped: list[Article] = []
        for article in articles:
            entry = manifest.get(article.slug)
            if platforms_done_for(entry, args.platform):
                skipped.append(article)
            else:
                remaining.append(article)
        for article in skipped:
            entry = manifest.get(article.slug)
            print(
                f"SKIP {article.slug}: already in {MANIFEST_PATH.name} "
                f"({recorded_ids_summary(entry)}). Use --force to republish."
            )
        articles = remaining

    if not articles:
        print("Nothing to publish.")
        return

    if args.newest_first:
        articles = sorted(articles, key=lambda item: item.date, reverse=True)
    else:
        articles = sorted(articles, key=lambda item: item.date)

    mode = "Dry run" if args.dry_run else "Publishing"
    print(f"{mode} {len(articles)} article(s) to {args.platform} ...")

    for index, article in enumerate(articles, start=1):
        print(f"\n[{index}/{len(articles)}] {article.date} — {article.slug} — {article.title}")
        try:
            publish_one(
                config,
                client,
                article,
                platform=args.platform,
                dry_run=args.dry_run,
                force=force,
                manifest=manifest,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR: {exc}")
            if args.stop_on_error:
                raise SystemExit(1) from exc
            continue

        if args.delay and index < len(articles) and not args.dry_run:
            time.sleep(args.delay)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Publish articles.json entries to Facebook and Instagram."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    auth_parser = subparsers.add_parser("auth", help="Exchange a User token and save Page/IG tokens")
    auth_parser.add_argument(
        "--token",
        help="Short-lived User access token (otherwise prompted)",
    )

    list_parser = subparsers.add_parser("list", help="List articles and publish status")
    list_parser.add_argument("--slug", help="Filter to one slug")
    list_parser.add_argument("--date", help="Filter to YYYY-MM-DD")
    list_parser.add_argument("--from-date", help="Include articles on/after YYYY-MM-DD")
    list_parser.add_argument("--to-date", help="Include articles on/before YYYY-MM-DD")

    publish_parser = subparsers.add_parser("publish", help="Publish selected articles")
    publish_parser.add_argument("--slug", help="Publish one article by slug")
    publish_parser.add_argument("--date", help="Publish articles on YYYY-MM-DD")
    publish_parser.add_argument("--from-date", help="Publish articles on/after YYYY-MM-DD")
    publish_parser.add_argument("--to-date", help="Publish articles on/before YYYY-MM-DD")
    publish_parser.add_argument(
        "--platform",
        default="both",
        choices=["facebook", "instagram", "both"],
        help="Target platform (default: both)",
    )
    publish_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve captions/images without calling Meta",
    )
    publish_parser.add_argument(
        "--force",
        action="store_true",
        help="Republish even when facebook/instagram ids are already in published.json",
    )
    publish_parser.add_argument(
        "--skip-published",
        action="store_true",
        help=argparse.SUPPRESS,  # kept for compatibility; skipping is now the default
    )
    publish_parser.add_argument(
        "--newest-first",
        action="store_true",
        help="Publish newest articles first (default: oldest first)",
    )
    publish_parser.add_argument(
        "--delay",
        type=float,
        default=3.0,
        help="Seconds to wait between articles (default: 3)",
    )
    publish_parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop immediately if an article fails",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "list":
        config = load_config(require_credentials=False)
        cmd_list(config, args)
        return

    if args.command == "publish" and args.dry_run:
        config = load_config(require_credentials=False)
        cmd_publish(config, None, args)
        return

    config = load_config()
    client = MetaClient(config)

    if args.command == "auth":
        cmd_auth(client, args)
    elif args.command == "publish":
        cmd_publish(config, client, args)
    else:
        parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
