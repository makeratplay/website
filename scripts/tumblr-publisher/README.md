# Tumblr Publisher

Publish progress blog posts from a Maker At Play project page (for example `projects/64/index.html`) to [mlhblog.tumblr.com](https://mlhblog.tumblr.com/) via the Tumblr API.

The tool parses each `div.blog-post` block in the HTML, uploads local images, embeds YouTube videos, and creates NPF (Neue Post Format) text posts on Tumblr.

## Requirements

- Python 3.10+
- A Tumblr OAuth application with `write` and `offline_access` scopes

## Setup

### 1. Register a Tumblr app

1. Go to [tumblr.com/oauth/apps](https://www.tumblr.com/oauth/apps) and create an application.
2. Set the OAuth2 redirect URI to match your config (default: `http://127.0.0.1:8765/callback`).
3. Note your **OAuth consumer key** and **secret key**.

### 2. Configure environment

```powershell
cd scripts\tumblr-publisher
copy config.example.env .env
```

Edit `.env` with your Tumblr credentials and project paths. See [Configuration](#configuration) below.

### 3. Install dependencies

```powershell
pip install -r requirements.txt
```

### 4. Authenticate once

```powershell
python publish.py auth
```

This opens a browser, asks you to authorize the app, and saves tokens to `token.json`. Re-run only if authentication expires or fails.

## Usage

All commands are run from `scripts/tumblr-publisher/`.

### List posts

Parse the project HTML and show publish status. Does not require Tumblr credentials.

```powershell
python publish.py list
python publish.py list --date 2026-06-30
```

Status values:

| Status | Meaning |
|--------|---------|
| `ready` | Has content and has not been published yet |
| `placeholder` | Skipped (e.g. "Write-up coming soon") |
| `published (123456789…)` | Already recorded in `published.json` |

### Publish posts

```powershell
# Preview payload without calling Tumblr
python publish.py publish --date 2026-06-30 --dry-run

# Publish one post (backdated to that day)
python publish.py publish --date 2026-06-30

# Publish all unpublished posts, oldest first
python publish.py publish --skip-published

# Publish as drafts first (useful for bulk review)
python publish.py publish --skip-published --state draft

# Publish a date range
python publish.py publish --from-date 2026-06-01 --to-date 2026-06-30 --skip-published
```

#### Publish options

| Option | Description |
|--------|-------------|
| `--date YYYY-MM-DD` | Publish a single post by date |
| `--from-date YYYY-MM-DD` | Include posts on or after this date |
| `--to-date YYYY-MM-DD` | Include posts on or before this date |
| `--state` | `published` (default), `draft`, `queue`, or `private` |
| `--dry-run` | Build the API payload without posting |
| `--skip-published` | Skip dates already in `published.json` |
| `--newest-first` | Publish newest posts first (default: oldest first) |
| `--delay SECONDS` | Pause between posts (default: 3) |
| `--stop-on-error` | Stop immediately if a post fails |

## Configuration

Settings live in `.env` (copy from `config.example.env`):

| Variable | Description |
|----------|-------------|
| `TUMBLR_CLIENT_ID` | OAuth consumer key |
| `TUMBLR_CLIENT_SECRET` | OAuth consumer secret |
| `TUMBLR_REDIRECT_URI` | Must match your Tumblr app redirect URI |
| `TUMBLR_BLOG` | Target blog (default: `mlhblog.tumblr.com`) |
| `TUMBLR_TAGS` | Comma-separated tags added to every post |
| `PROJECT_HTML` | Path to project page, relative to repo root |
| `PROJECT_DIR` | Directory containing post images, relative to repo root |
| `SOURCE_URL` | Content source link on Tumblr (default: project page URL) |

## State files

These JSON files track authentication and publishing progress. They are gitignored and stay on your machine.

### `token.json`

Created by `python publish.py auth`. Stores OAuth2 tokens for API access.

```json
{
  "access_token": "...",
  "refresh_token": "...",
  "expires_at": 1782957193.49,
  "scope": "basic write offline_access"
}
```

| Field | Purpose |
|-------|---------|
| `access_token` | Bearer token sent with each API request |
| `refresh_token` | Used to obtain a new access token when the current one expires |
| `expires_at` | Unix timestamp; the client refreshes automatically before this time |
| `scope` | Granted OAuth scopes |

**When to delete:** If auth breaks or you switch Tumblr accounts, delete this file and run `auth` again.

### `published.json`

Updated after each successful publish. Maps each blog post date to its Tumblr post ID so reruns can skip already-published entries.

```json
{
  "2026-06-30": {
    "id": "820989016762728448",
    "title": "June 30, 2026 – Every Project Has a Mistake",
    "state": "published"
  }
}
```

| Field | Purpose |
|-------|---------|
| Key (`YYYY-MM-DD`) | Post date from the HTML heading |
| `id` | Tumblr post ID returned by the API |
| `title` | Post title at time of publish |
| `state` | Tumblr state used when published (`published`, `draft`, etc.) |

**Republishing a post:** Delete that date's entry from `published.json` (and optionally delete the post on Tumblr), then run `publish --date YYYY-MM-DD` again. Without `--skip-published`, a date in the manifest is still published again—the manifest is only consulted when `--skip-published` is set.

## What gets posted

For each blog entry the tool sends:

- **Title** — bold regular text (not Tumblr's large heading style)
- **Body** — one NPF text block per `<p>` or list item; line breaks from HTML source formatting are collapsed within each paragraph
- **Images** — uploaded from `PROJECT_DIR` (local files referenced in the HTML)
- **YouTube** — embedded via Tumblr's YouTube provider when an iframe or link is present
- **Tags** — from `TUMBLR_TAGS` in `.env`
- **Content source** — from `SOURCE_URL` (links back to the project page)
- **Date** — backdated to the post's heading date at noon UTC

Placeholder posts (e.g. "Write-up coming soon") are skipped automatically.

## Project layout

```
scripts/tumblr-publisher/
├── README.md           # This file
├── config.example.env  # Template for .env
├── .env                # Your credentials (gitignored)
├── token.json          # OAuth tokens (gitignored)
├── published.json      # Publish manifest (gitignored)
├── requirements.txt
├── publish.py          # CLI entry point
├── parse_posts.py      # HTML parser
└── tumblr_client.py    # Tumblr OAuth + API client
```

## Troubleshooting

**Missing env vars** — Copy `config.example.env` to `.env` and fill in `TUMBLR_CLIENT_ID` and `TUMBLR_CLIENT_SECRET`.

**OAuth callback fails** — Ensure `TUMBLR_REDIRECT_URI` in `.env` exactly matches the redirect URI in your Tumblr app settings. The default uses port `8765`; nothing else should be listening on that port during `auth`.

**Missing image** — The image file must exist under `PROJECT_DIR`. Commit and deploy site assets if you want them hosted on makeratplay.com as well.

**Daily post limit** — Tumblr may rate-limit bulk publishing. Use `--state draft` or `--state queue`, or increase `--delay`.

**Token expired** — Usually handled automatically. If requests fail with 401, delete `token.json` and run `auth` again.
