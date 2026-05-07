# Etsy Spreadsheet Agent

Conversational agent that designs Excel/Google-Sheets digital products and posts them to Etsy as **drafts** for human review. Designed for the restaurant operator toolkit niche but works for any spreadsheet-based digital product.

## What it does

1. You describe a product in plain English ("food cost calculator with menu pricing built in")
2. Claude designs the spreadsheet structure (sheets, columns, formulas, sample data)
3. `openpyxl` materializes a real .xlsx file
4. Pillow generates two listing preview images (cover + features)
5. Claude writes SEO-optimized title / description / tags
6. The agent uploads everything to Etsy as a **draft** — never auto-published
7. You review on Etsy, then ask the agent to publish when ready

## Why drafts only

Per recent research, Etsy's 2026 algorithm penalizes bulk uploaders — shops posting <5 high-quality items per week now outrank shops posting 50/day. Auto-publishing also risks ToS issues. Drafts + manual approval matches the pattern the algorithm rewards.

## Setup

### 1. Install

```bash
cd "/Users/a.j.marisi/Documents/Agent #1/agents/etsy_spreadsheet_agent"
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env`:

- **`ANTHROPIC_API_KEY`** — from https://console.anthropic.com
- **`ETSY_CLIENT_ID`** — register an app at https://www.etsy.com/developers/your-apps. Use the "keystring". Note: Etsy may require manual approval for new apps.
- **`ETSY_REDIRECT_URI`** — leave as `http://localhost:8765/callback` (must match what you registered in the Etsy app)

### 3. Authorize

From the parent directory (so the package import works):

```bash
cd "/Users/a.j.marisi/Documents/Agent #1/agents"
python -m etsy_spreadsheet_agent.cli auth
```

This opens your browser, you grant the scopes, and the script writes the access/refresh tokens back to `.env`.

### 4. Chat with the agent

```bash
python -m etsy_spreadsheet_agent.cli chat
```

Example session:

```
you ▸ Build a food cost and menu pricing calculator for independent restaurants. Should include ingredient cost tracker, recipe cost rollup, and a menu pricing sheet that flags items below 30% target food cost.

  [tool] create_spreadsheet({"brief":"Food cost ..."})
  [tool] generate_listing_assets({...})
  [tool] draft_listing_copy({...})
  [tool] create_etsy_draft({...})

agent ▸ Draft created — listing 1234567890. Review at https://www.etsy.com/your/shops/me/tools/listings/1234567890
        Tell me to "publish 1234567890" once you've reviewed.

you ▸ publish 1234567890

  [tool] publish_listing({"listing_id":1234567890})

agent ▸ Live: https://www.etsy.com/listing/1234567890
```

## Tools the agent has

| Tool                       | What it does                                              |
|---------------------------|-----------------------------------------------------------|
| `create_spreadsheet`      | Designs + builds an .xlsx from a brief                    |
| `generate_listing_assets` | Creates 2000×2000 cover + features images                |
| `draft_listing_copy`      | SEO title/description/tags via Claude                     |
| `create_etsy_draft`       | Uploads to Etsy as a draft (never published)              |
| `publish_listing`         | Sets state=active — only after explicit user OK           |
| `update_listing`          | Patch title/description/price/tags                        |
| `list_my_listings`        | Show shop listings filtered by state                      |
| `recent_sales`            | Pull recent receipts                                      |

## Files

- `agent.py` — Claude tool runner + tool implementations
- `cli.py` — entry point (`auth`, `chat`, `listings`)
- `config.py` — env var loading + `.env` persistence
- `db.py` — SQLite state (tracks generated spreadsheets and listings)
- `tools/etsy_client.py` — OAuth 2.0 PKCE + Etsy v3 API wrapper
- `tools/spreadsheet_builder.py` — Claude designs schema, openpyxl builds .xlsx
- `tools/mockup_generator.py` — Pillow-based preview images
- `output/` — generated .xlsx files and PNG previews
- `state.db` — SQLite, created on first run

## Notes / gotchas

- **Etsy API approval** — first-party apps may need manual review by Etsy before write scopes work. Read scopes are usually instant.
- **Taxonomy ID** — `create_draft_listing` defaults to `taxonomy_id=6735` (Digital Prints). For "Templates" or other categories, pass a different ID. Get the full list via `GET /application/seller-taxonomy/nodes`.
- **Token refresh** — access tokens expire in ~1 hour; the client auto-refreshes using the refresh token (90-day expiry). If the refresh token expires you'll need to re-run `auth`.
- **Rate limits** — Etsy allows 10 requests/sec / 10k/day per app. The agent doesn't batch aggressively, so you shouldn't hit them.
- **Mockups are basic** — the Pillow-generated images are clean but not designer-quality. Replace with Canva or screenshot a real Google Sheets render once you have a winning niche.
