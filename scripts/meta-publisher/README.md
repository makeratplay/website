# Meta Publisher (Facebook + Instagram)

Publish selected entries from [`content/articles.json`](../../content/articles.json) to the [Maker At Play Facebook Page](https://www.facebook.com/makeratplay) and [Instagram](https://www.instagram.com/makeratplay/) via the Meta Graph API.

The tool mirrors the Tumblr publisher workflow: authenticate once, list what is ready, dry-run a payload, then publish by slug or date range. A local `published.json` records each platform’s post id **keyed by article slug**. Reruns skip any platform that already has an id, so duplicates are not created unless you pass `--force`.

The whole catalog is never published in one shot. `publish` requires `--slug`, `--date`, `--from-date`, and/or `--to-date`.

## Requirements

- Python 3.10+
- A Meta (Facebook) app you admin
- Facebook Page `makeratplay` (you must be a Page admin)
- Instagram `@makeratplay` converted to a **professional** account and **linked to that Page**

## One-time Meta setup

### 1. Link Instagram to the Page

1. In Instagram, switch `@makeratplay` to a Professional account (Creator or Business) if it is not already.
2. Connect it to the Facebook Page [makeratplay](https://www.facebook.com/makeratplay) (Meta Business Suite or Page settings → Instagram).
3. Confirm the Page shows a linked Instagram professional account.

Without this link, Graph API returns no `instagram_business_account` and auth will stop with a clear error.

### 2. Create a Meta app

1. Open [developers.facebook.com/apps](https://developers.facebook.com/apps/) and create an app (type **Business** is fine).
2. Add the **Facebook Login** product if prompted (needed for user tokens).
3. Development mode is enough when you are an admin of the app and the Page. App Review is not required for posting to your own Page.
4. Note the **App ID** and **App Secret**.

### 3. Configure environment

```powershell
cd scripts\meta-publisher
copy config.example.env .env
```

Edit `.env`:

| Variable | Description |
|----------|-------------|
| `META_APP_ID` | App ID |
| `META_APP_SECRET` | App Secret |
| `META_PAGE_ID` | Page id or name (default `makeratplay`) |
| `SITE_BASE_URL` | Origin for relative article/image paths (default `https://makeratplay.com`) |
| `META_HASHTAGS` | Space-separated hashtags appended to captions |
| `META_GRAPH_VERSION` | Graph API version (default `v21.0`) |

### 4. Install dependencies

```powershell
pip install -r requirements.txt
```

### 5. Authenticate once

1. Open [Graph API Explorer](https://developers.facebook.com/tools/explorer/).
2. Select your app.
3. Generate a **User** token with these permissions:
   - `pages_show_list`
   - `pages_read_engagement`
   - `pages_manage_posts`
   - `instagram_basic`
   - `instagram_content_publish`
4. Run:

```powershell
python publish.py auth
```

Paste the short-lived User token when prompted (or pass `--token ...`).

The script exchanges it for a long-lived User token, finds the Page, stores the **Page access token**, and looks up the linked Instagram professional account id. Tokens are written to `token.json` (gitignored).

Re-run `auth` if the User token expires or you change Page/Instagram linkage. Page tokens obtained from a long-lived User token typically do not expire while you remain a Page admin.

## Usage

All commands run from `scripts/meta-publisher/`.

### List articles

```powershell
python publish.py list
python publish.py list --slug new-york-harbor-more-track
python publish.py list --from-date 2026-11-01
```

Credentials are not required for `list`.

### Dry run

```powershell
python publish.py publish --slug new-york-harbor-more-track --dry-run
```

Prints the caption, resolved article URL, local/remote image notes, and whether letterboxing is required. Does not call Meta.

### Publish

```powershell
# Both platforms
python publish.py publish --slug new-york-harbor-more-track

# Facebook only
python publish.py publish --slug new-york-harbor-more-track --platform facebook

# Instagram only
python publish.py publish --slug new-york-harbor-more-track --platform instagram

# Date range (already-published slugs are skipped automatically)
python publish.py publish --from-date 2026-11-01 --to-date 2026-11-11 --newest-first

# Force a fresh post even though ids are recorded
python publish.py publish --slug new-york-harbor-more-track --force
```

#### Publish options

| Option | Description |
|--------|-------------|
| `--slug` | One article by slug |
| `--date YYYY-MM-DD` | Articles on that date |
| `--from-date` / `--to-date` | Inclusive date range |
| `--platform` | `both` (default), `facebook`, or `instagram` |
| `--dry-run` | Resolve payload only |
| `--force` | Republish even when ids are already in `published.json` |
| `--newest-first` | Newest first (default: oldest first) |
| `--delay SECONDS` | Pause between articles (default: 3) |
| `--stop-on-error` | Exit on first failure |

## What gets posted

Same caption on Facebook and Instagram:

- Title
- Summary
- Absolute article URL
- Optional hashtags from `META_HASHTAGS`

Instagram captions do not make the URL tappable. Facebook does.

Neither platform is backdated; the article `date` is only used for selection.

### Facebook

`POST /{page-id}/photos` with caption. Local files are uploaded when present; otherwise a public image URL is used.

### Instagram

`POST /{ig-user-id}/media` with a **public** `image_url`, then `media_publish` after the container status is `FINISHED`.

Instagram requires aspect ratio between **4:5** and **1.91:1**. Images outside that range are letterboxed (black bars) to the nearest allowed ratio, long edge 1080, JPEG under `prepared/`. Letterboxed bytes are uploaded to Facebook first; Instagram then uses the Facebook CDN URL.

If Instagram is requested alone and the image is not publicly reachable (and letterboxing cannot stage via Facebook), the tool stops with an error instead of inventing a host.

If one platform succeeds and the other fails, the successful id is written to `published.json` immediately under that slug. Re-run the same `--slug` (without `--force`) to finish only the missing side; platforms that already have an id are skipped.

## State files

Gitignored; stay on your machine.

### `token.json`

Created by `python publish.py auth`.

| Field | Purpose |
|-------|---------|
| `user_access_token` | Long-lived User token |
| `user_token_expires_at` | Unix expiry (if provided) |
| `page_id` / `page_name` | Target Page |
| `page_access_token` | Token used for Page and IG publish calls |
| `ig_user_id` / `ig_username` | Linked Instagram professional account |

### `published.json`

Updated after each successful platform publish. Keyed by article `slug`. This is the duplicate guard: a second `publish --slug …` prints `SKIP` and does nothing if both requested platforms already have ids.

```json
{
  "new-york-harbor-more-track": {
    "title": "New York Harbor Layout: More Track...",
    "date": "2026-11-11",
    "facebook": { "id": "123...", "post_id": "456_123...", "published": true },
    "instagram": { "id": "456...", "container_id": "789..." }
  }
}
```

| Field | Purpose |
|-------|---------|
| Key (`slug`) | Article slug from `articles.json` |
| `facebook.id` | Facebook photo id |
| `facebook.post_id` | Feed post id when Graph returns it |
| `instagram.id` | Instagram media id |
| `instagram.container_id` | Container used for `media_publish` |

To republish one side, delete that platform object for the slug (and optionally delete the live post), then run `publish` again — or pass `--force` to create a new post and overwrite the recorded id.

## Project layout

```
scripts/meta-publisher/
├── README.md
├── config.example.env
├── .env                 # gitignored
├── token.json           # gitignored
├── published.json       # gitignored
├── prepared/            # letterboxed JPEGs (gitignored except .gitkeep)
├── requirements.txt
├── publish.py           # CLI
├── articles.py          # articles.json + captions + letterbox
└── meta_client.py       # Graph API auth + publish
```

## Troubleshooting

**Missing env vars** — Copy `config.example.env` to `.env` and set `META_APP_ID` / `META_APP_SECRET`.

**No Instagram business account** — `@makeratplay` must be professional and linked to the Page. Re-run `auth` after linking.

**Instagram image URL not reachable** — Relative site images must already be live at `SITE_BASE_URL`, or publish Facebook first so a CDN URL is available. Letterboxed images always go through Facebook upload.

**Aspect ratio error from Instagram** — Confirm letterboxing ran (`prepared/{slug}.jpg`). Re-run with `--dry-run` to see ratio notes.

**(#10) / permission errors** — Regenerate the User token in Graph API Explorer with all listed scopes and run `auth` again.

**Daily limits** — Instagram enforces publish rate limits. Use `--delay` and avoid large date ranges in one sitting.
