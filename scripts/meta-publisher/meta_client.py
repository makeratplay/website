"""Meta Graph API client for Facebook Page and Instagram publishing."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

USER_AGENT = "MakerAtPlay-MetaPublisher/1.0"
SCOPES = [
    "pages_show_list",
    "pages_read_engagement",
    "pages_manage_posts",
    "instagram_basic",
    "instagram_content_publish",
]


@dataclass
class MetaConfig:
    app_id: str
    app_secret: str
    page_id: str
    site_base_url: str
    hashtags: list[str]
    graph_version: str
    token_path: Path
    articles_path: Path
    prepared_dir: Path
    repo_root: Path


@dataclass
class TokenBundle:
    user_access_token: str
    user_token_expires_at: float | None
    page_id: str
    page_name: str
    page_access_token: str
    ig_user_id: str | None
    ig_username: str | None

    def to_json(self) -> dict[str, Any]:
        return {
            "user_access_token": self.user_access_token,
            "user_token_expires_at": self.user_token_expires_at,
            "page_id": self.page_id,
            "page_name": self.page_name,
            "page_access_token": self.page_access_token,
            "ig_user_id": self.ig_user_id,
            "ig_username": self.ig_username,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> TokenBundle:
        return cls(
            user_access_token=payload["user_access_token"],
            user_token_expires_at=payload.get("user_token_expires_at"),
            page_id=payload["page_id"],
            page_name=payload.get("page_name", ""),
            page_access_token=payload["page_access_token"],
            ig_user_id=payload.get("ig_user_id"),
            ig_username=payload.get("ig_username"),
        )


class MetaClient:
    def __init__(self, config: MetaConfig) -> None:
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.tokens: TokenBundle | None = None
        if config.token_path.exists():
            self.tokens = TokenBundle.from_json(
                json.loads(config.token_path.read_text(encoding="utf-8"))
            )

    @property
    def graph_base(self) -> str:
        return f"https://graph.facebook.com/{self.config.graph_version}"

    def _save_tokens(self) -> None:
        if not self.tokens:
            return
        self.config.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.config.token_path.write_text(
            json.dumps(self.tokens.to_json(), indent=2),
            encoding="utf-8",
        )

    def _graph_get(
        self,
        path: str,
        *,
        access_token: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        query = dict(params or {})
        query["access_token"] = access_token
        response = self.session.get(f"{self.graph_base}{path}", params=query, timeout=60)
        return self._parse_response(response)

    def _graph_post(
        self,
        path: str,
        *,
        access_token: str,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = dict(data or {})
        payload["access_token"] = access_token
        response = self.session.post(
            f"{self.graph_base}{path}",
            data=payload,
            files=files,
            timeout=120,
        )
        return self._parse_response(response)

    @staticmethod
    def _parse_response(response: requests.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(
                f"Meta API returned non-JSON ({response.status_code}): {response.text[:500]}"
            ) from exc
        if response.status_code >= 400 or "error" in payload:
            error = payload.get("error", {})
            message = error.get("message") or response.text
            code = error.get("code")
            raise RuntimeError(f"Meta API error (HTTP {response.status_code}, code {code}): {message}")
        return payload

    def authenticate(self, short_lived_user_token: str | None = None) -> TokenBundle:
        if not short_lived_user_token:
            print(
                "Generate a short-lived User access token in Graph API Explorer with scopes:\n"
                f"  {', '.join(SCOPES)}\n"
                "https://developers.facebook.com/tools/explorer/\n"
            )
            short_lived_user_token = input("Paste short-lived User access token: ").strip()
        if not short_lived_user_token:
            raise SystemExit("No token provided.")

        print("Exchanging for long-lived User token...")
        response = self.session.get(
            f"{self.graph_base}/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": self.config.app_id,
                "client_secret": self.config.app_secret,
                "fb_exchange_token": short_lived_user_token,
            },
            timeout=60,
        )
        exchanged = self._parse_response(response)
        user_token = exchanged["access_token"]
        expires_in = exchanged.get("expires_in")
        expires_at = time.time() + float(expires_in) - 60 if expires_in else None

        pages = self._graph_get(
            "/me/accounts",
            access_token=user_token,
            params={"fields": "id,name,access_token,instagram_business_account{id,username}"},
        )
        data = pages.get("data") or []
        if not data:
            raise SystemExit(
                "No Facebook Pages returned. Confirm the token user is an admin of the Page "
                "and that pages_show_list is granted."
            )

        target = self.config.page_id.strip().lower()
        page = None
        for entry in data:
            if entry.get("id") == self.config.page_id or entry.get("name", "").lower() == target:
                page = entry
                break
            # vanity / username match via name containing makeratplay
            if target and target in entry.get("name", "").lower().replace(" ", ""):
                page = entry
                break

        if page is None and len(data) == 1:
            page = data[0]
            print(f"Using the only available Page: {page.get('name')} ({page.get('id')})")
        elif page is None:
            listing = "\n".join(f"  {p.get('id')}  {p.get('name')}" for p in data)
            raise SystemExit(
                f"Could not find Page matching {self.config.page_id!r}. Available Pages:\n{listing}"
            )

        ig = page.get("instagram_business_account") or {}
        ig_user_id = ig.get("id")
        ig_username = ig.get("username")
        if not ig_user_id:
            # Try an explicit Page lookup; sometimes nested field is empty on /me/accounts.
            detail = self._graph_get(
                f"/{page['id']}",
                access_token=page["access_token"],
                params={"fields": "id,name,instagram_business_account{id,username}"},
            )
            ig = detail.get("instagram_business_account") or {}
            ig_user_id = ig.get("id")
            ig_username = ig.get("username")

        if not ig_user_id:
            raise SystemExit(
                f"Page {page.get('name')} ({page.get('id')}) has no linked Instagram professional "
                "account. Convert @makeratplay to a professional account and connect it to this Page, "
                "then run auth again."
            )

        self.tokens = TokenBundle(
            user_access_token=user_token,
            user_token_expires_at=expires_at,
            page_id=str(page["id"]),
            page_name=str(page.get("name", "")),
            page_access_token=str(page["access_token"]),
            ig_user_id=str(ig_user_id),
            ig_username=str(ig_username) if ig_username else None,
        )
        self._save_tokens()
        print(
            f"Saved tokens for Page {self.tokens.page_name} ({self.tokens.page_id}) "
            f"and Instagram @{self.tokens.ig_username or self.tokens.ig_user_id}"
        )
        return self.tokens

    def require_tokens(self) -> TokenBundle:
        if not self.tokens:
            raise RuntimeError("Not authenticated. Run: python publish.py auth")
        return self.tokens

    def create_facebook_photo(
        self,
        *,
        caption: str,
        image_path: Path | None = None,
        image_url: str | None = None,
        published: bool = True,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        tokens = self.require_tokens()
        if dry_run:
            return {
                "dry_run": True,
                "platform": "facebook",
                "published": published,
                "image_path": str(image_path) if image_path else None,
                "image_url": image_url,
                "caption_chars": len(caption),
            }

        data: dict[str, Any] = {
            "caption": caption,
            "published": "true" if published else "false",
        }
        files = None
        if image_path is not None:
            files = {"source": (image_path.name, image_path.read_bytes(), "image/jpeg")}
        elif image_url:
            data["url"] = image_url
        else:
            raise ValueError("Facebook photo requires image_path or image_url")

        payload = self._graph_post(
            f"/{tokens.page_id}/photos",
            access_token=tokens.page_access_token,
            data=data,
            files=files,
        )
        photo_id = str(payload.get("id") or "")
        post_id = payload.get("post_id")
        if not photo_id and post_id:
            photo_id = str(post_id)
        if not photo_id:
            raise RuntimeError(f"Facebook photo response missing id: {payload}")
        result: dict[str, Any] = {"id": photo_id, "raw": payload, "published": published}
        if post_id:
            result["post_id"] = str(post_id)
        return result

    def facebook_photo_cdn_url(self, photo_id: str) -> str:
        tokens = self.require_tokens()
        payload = self._graph_get(
            f"/{photo_id}",
            access_token=tokens.page_access_token,
            params={"fields": "images"},
        )
        images = payload.get("images") or []
        if not images:
            raise RuntimeError(f"No CDN images returned for photo {photo_id}")
        # Prefer largest width.
        best = max(images, key=lambda item: int(item.get("width") or 0))
        url = best.get("source")
        if not url:
            raise RuntimeError(f"CDN image missing source for photo {photo_id}")
        return str(url)

    def create_instagram_media(
        self,
        *,
        caption: str,
        image_url: str,
        dry_run: bool = False,
        poll_interval: float = 2.0,
        poll_timeout: float = 120.0,
    ) -> dict[str, Any]:
        tokens = self.require_tokens()
        if not tokens.ig_user_id:
            raise RuntimeError("No Instagram user id in token.json. Re-run auth.")

        if dry_run:
            return {
                "dry_run": True,
                "platform": "instagram",
                "image_url": image_url,
                "caption_chars": len(caption),
            }

        container = self._graph_post(
            f"/{tokens.ig_user_id}/media",
            access_token=tokens.page_access_token,
            data={"image_url": image_url, "caption": caption},
        )
        creation_id = str(container.get("id", ""))
        if not creation_id:
            raise RuntimeError(f"Instagram container missing id: {container}")

        deadline = time.time() + poll_timeout
        status = "IN_PROGRESS"
        while time.time() < deadline:
            status_payload = self._graph_get(
                f"/{creation_id}",
                access_token=tokens.page_access_token,
                params={"fields": "status_code,status"},
            )
            status = str(status_payload.get("status_code") or "")
            if status == "FINISHED":
                break
            if status == "ERROR":
                raise RuntimeError(f"Instagram container failed: {status_payload}")
            time.sleep(poll_interval)
        else:
            raise RuntimeError(
                f"Timed out waiting for Instagram container {creation_id} (last status={status})"
            )

        published = self._graph_post(
            f"/{tokens.ig_user_id}/media_publish",
            access_token=tokens.page_access_token,
            data={"creation_id": creation_id},
        )
        media_id = str(published.get("id", ""))
        if not media_id:
            raise RuntimeError(f"Instagram publish missing id: {published}")
        return {
            "id": media_id,
            "container_id": creation_id,
            "raw": published,
        }
