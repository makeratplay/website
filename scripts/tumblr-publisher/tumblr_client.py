"""Tumblr OAuth2 client and NPF post creation."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import secrets
import tempfile
import threading
import time
import urllib.parse
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import requests
from PIL import Image

from parse_posts import BlogPost, ImageBlock, TextBlock, VideoBlock

API_BASE = "https://api.tumblr.com/v2"
AUTH_URL = "https://www.tumblr.com/oauth2/authorize"
TOKEN_URL = f"{API_BASE}/oauth2/token"
USER_AGENT = "MakerAtPlay-TumblrPublisher/1.0"


@dataclass
class TumblrConfig:
    client_id: str
    client_secret: str
    redirect_uri: str
    blog: str
    tags: list[str]
    project_dir: Path
    token_path: Path
    source_url: str


@dataclass
class TokenBundle:
    access_token: str
    refresh_token: str
    expires_at: float
    scope: str

    @classmethod
    def from_response(cls, payload: dict[str, Any]) -> TokenBundle:
        return cls(
            access_token=payload["access_token"],
            refresh_token=payload["refresh_token"],
            expires_at=time.time() + float(payload.get("expires_in", 2520)) - 60,
            scope=payload.get("scope", ""),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "scope": self.scope,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> TokenBundle:
        return cls(
            access_token=payload["access_token"],
            refresh_token=payload["refresh_token"],
            expires_at=float(payload["expires_at"]),
            scope=payload.get("scope", ""),
        )


class TumblrClient:
    def __init__(self, config: TumblrConfig) -> None:
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.tokens: TokenBundle | None = None
        if config.token_path.exists():
            self.tokens = TokenBundle.from_json(
                json.loads(config.token_path.read_text(encoding="utf-8"))
            )

    def _save_tokens(self) -> None:
        if not self.tokens:
            return
        self.config.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.config.token_path.write_text(
            json.dumps(self.tokens.to_json(), indent=2),
            encoding="utf-8",
        )

    def _refresh_access_token(self) -> None:
        if not self.tokens:
            raise RuntimeError("Not authenticated. Run: python publish.py auth")
        response = self.session.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.tokens.refresh_token,
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
            },
            timeout=60,
        )
        response.raise_for_status()
        self.tokens = TokenBundle.from_response(response.json())
        self._save_tokens()

    def _ensure_token(self) -> str:
        if not self.tokens:
            raise RuntimeError("Not authenticated. Run: python publish.py auth")
        if time.time() >= self.tokens.expires_at:
            self._refresh_access_token()
        return self.tokens.access_token

    def authenticate(self) -> None:
        state = secrets.token_urlsafe(16)
        auth_code: dict[str, str] = {}

        class CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                parsed = urllib.parse.urlparse(self.path)
                params = urllib.parse.parse_qs(parsed.query)
                if parsed.path != urllib.parse.urlparse(config.redirect_uri).path:
                    self.send_response(404)
                    self.end_headers()
                    return

                if "error" in params:
                    auth_code["error"] = params["error"][0]
                else:
                    auth_code["code"] = params.get("code", [""])[0]
                    auth_code["state"] = params.get("state", [""])[0]

                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                if "error" in auth_code:
                    body = f"<h1>Tumblr auth failed</h1><p>{auth_code['error']}</p>"
                else:
                    body = "<h1>Tumblr auth complete</h1><p>You can close this tab.</p>"
                self.wfile.write(body.encode("utf-8"))

                threading.Thread(target=self.server.shutdown, daemon=True).start()

            def log_message(self, format: str, *args: Any) -> None:
                return

        config = self.config
        query = urllib.parse.urlencode(
            {
                "client_id": config.client_id,
                "response_type": "code",
                "scope": "basic write offline_access",
                "state": state,
                "redirect_uri": config.redirect_uri,
            }
        )
        authorize_url = f"{AUTH_URL}?{query}"
        print(f"Opening browser for Tumblr authorization:\n{authorize_url}")
        webbrowser.open(authorize_url)

        redirect = urllib.parse.urlparse(config.redirect_uri)
        server = HTTPServer((redirect.hostname or "127.0.0.1", redirect.port or 8765), CallbackHandler)
        print(f"Waiting for OAuth callback on {config.redirect_uri} ...")
        server.handle_request()

        if auth_code.get("error"):
            raise RuntimeError(f"Tumblr authorization failed: {auth_code['error']}")
        if auth_code.get("state") != state:
            raise RuntimeError("OAuth state mismatch; try again.")
        if not auth_code.get("code"):
            raise RuntimeError("No authorization code received.")

        response = self.session.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": auth_code["code"],
                "client_id": config.client_id,
                "client_secret": config.client_secret,
                "redirect_uri": config.redirect_uri,
            },
            timeout=60,
        )
        response.raise_for_status()
        self.tokens = TokenBundle.from_response(response.json())
        self._save_tokens()
        print(f"Saved token to {config.token_path}")

    def list_posts(self) -> list[dict[str, Any]]:
        token = self._ensure_token()
        url = f"{API_BASE}/blog/{self.config.blog}/posts"
        posts: list[dict[str, Any]] = []
        offset = 0
        while True:
            response = self.session.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                params={"limit": 20, "offset": offset, "npf": "true"},
                timeout=60,
            )
            if not response.ok:
                raise RuntimeError(
                    f"Tumblr API error {response.status_code}: {response.text}"
                )
            batch = response.json()["response"]["posts"]
            if not batch:
                break
            posts.extend(batch)
            offset += len(batch)
            if len(batch) < 20:
                break
        return posts

    def _image_mime(self, path: Path) -> str:
        mime, _ = mimetypes.guess_type(path.name)
        return mime or "application/octet-stream"

    def _image_cache(self) -> Path:
        cache = Path(tempfile.gettempdir()) / "makeratplay-tumblr-images"
        cache.mkdir(parents=True, exist_ok=True)
        return cache

    def _download_image(self, url: str, filename: str) -> Path:
        safe_name = Path(urllib.parse.urlparse(url).path).name or filename or "image"
        dest = self._image_cache() / f"{hashlib.sha1(url.encode()).hexdigest()[:16]}-{safe_name}"
        if dest.exists() and dest.stat().st_size > 0:
            return dest
        response = self.session.get(url, timeout=120)
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "")
        if "text/html" in content_type:
            raise RuntimeError(f"Image URL returned HTML: {url}")
        dest.write_bytes(response.content)
        return dest

    def _prepare_image(self, path: Path) -> tuple[Path, int, int, str]:
        mime = self._image_mime(path)
        with Image.open(path) as img:
            width, height = img.size
            if img.format == "GIF" or (
                max(width, height) <= 2048 and path.stat().st_size <= 8_000_000
            ):
                return path, width, height, mime
            if img.mode in {"RGBA", "LA"} or (img.mode == "P" and "transparency" in img.info):
                rgba = img.convert("RGBA")
                converted = Image.new("RGB", rgba.size, (255, 255, 255))
                converted.paste(rgba, mask=rgba.split()[-1])
            else:
                converted = img.convert("RGB")
            converted.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
            digest = hashlib.sha1(str(path).encode()).hexdigest()[:10]
            dest = self._image_cache() / f"{digest}-{converted.size[0]}x{converted.size[1]}.jpg"
            if not dest.exists():
                converted.save(dest, "JPEG", quality=85, optimize=True)
            return dest, converted.size[0], converted.size[1], "image/jpeg"

    def _resolve_image(self, block: ImageBlock, post: BlogPost) -> Path:
        if block.path is not None and block.path.exists():
            return block.path
        local = self.config.project_dir / block.filename
        if block.url is None and local.exists():
            return local
        if block.url:
            return self._download_image(block.url, block.filename)
        location = block.path or local
        raise FileNotFoundError(f"Missing image for {post.date_key}: {location}")

    @staticmethod
    def _limit_formatting(formatting: list[dict] | None, link_budget: list[int]) -> list[dict] | None:
        if not formatting:
            return None
        kept: list[dict] = []
        for item in formatting:
            if item.get("type") == "link":
                if link_budget[0] >= 100:
                    continue
                link_budget[0] += 1
            kept.append(item)
        return kept or None

    def _build_npf_content(
        self, post: BlogPost
    ) -> tuple[list[dict[str, Any]], dict[str, Path]]:
        content: list[dict[str, Any]] = []
        uploads: dict[str, Path] = {}
        link_budget = [0]

        for index, block in enumerate(post.blocks):
            if isinstance(block, TextBlock):
                text = block.text
                if len(text) > 4096:
                    text = text[:4093] + "..."
                payload: dict[str, Any] = {"type": "text", "text": text}
                if block.subtype:
                    payload["subtype"] = block.subtype
                formatting = self._limit_formatting(block.formatting, link_budget)
                if formatting:
                    payload["formatting"] = formatting
                content.append(payload)
                continue

            if isinstance(block, ImageBlock):
                image_path = self._prepare_image(self._resolve_image(block, post))
                prepared, width, height, mime = image_path
                identifier = f"img-{post.manifest_key or post.date_key}-{index}"
                uploads[identifier] = prepared
                content.append(
                    {
                        "type": "image",
                        "alt_text": block.alt or None,
                        "media": [
                            {
                                "type": mime,
                                "identifier": identifier,
                                "width": width,
                                "height": height,
                            }
                        ],
                    }
                )
                continue

            if isinstance(block, VideoBlock):
                content.append(
                    {
                        "type": "video",
                        "provider": "youtube",
                        "url": block.url,
                        "embed_url": f"https://www.youtube.com/embed/{block.youtube_id}",
                        "metadata": {"id": block.youtube_id},
                    }
                )

        return content, uploads

    def create_post(
        self,
        post: BlogPost,
        *,
        state: str = "published",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        content, uploads = self._build_npf_content(post)
        tags = post.tags if post.tags is not None else self.config.tags
        payload: dict[str, Any] = {
            "content": content,
            "state": state,
            "tags": ", ".join(tags),
            "date": f"{post.post_date.isoformat()}T12:00:00Z",
            "source_url": post.source_url or self.config.source_url,
        }

        if dry_run:
            return {
                "dry_run": True,
                "title": post.title,
                "date": post.date_key,
                "state": state,
                "blocks": len(content),
                "uploads": [path.name for path in uploads.values()],
                "payload": payload,
            }

        access_token = self._ensure_token()
        url = f"{API_BASE}/blog/{self.config.blog}/posts"
        headers = {"Authorization": f"Bearer {access_token}"}

        if uploads:
            response = self.session.post(
                url,
                headers=headers,
                files=self._multipart_files(payload, uploads),
                timeout=300,
            )
        else:
            headers["Content-Type"] = "application/json"
            response = self.session.post(url, headers=headers, json=payload, timeout=120)

        if not response.ok:
            raise RuntimeError(
                f"Tumblr API error {response.status_code}: {response.text}"
            )

        body = response.json()
        return {
            "id": body["response"]["id"],
            "title": post.title,
            "date": post.date_key,
            "state": state,
        }

    @staticmethod
    def _multipart_files(
        payload: dict[str, Any], uploads: dict[str, Path]
    ) -> dict[str, tuple]:
        files: dict[str, tuple] = {
            "json": (None, json.dumps(payload), "application/json"),
        }
        for identifier, path in uploads.items():
            files[identifier] = (path.name, path.read_bytes(), mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        return files
