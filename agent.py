"""Conversational agent that creates, drafts, and manages Etsy spreadsheet listings.

Uses Claude's tool runner. Tools are local Python functions decorated with
@beta_tool. The agent never auto-publishes — listings are created in `draft`
state and require the user to run `publish_listing` explicitly.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

import anthropic
from anthropic import beta_tool

from . import config, db
from .tools import etsy_client, mockup_generator, spreadsheet_builder

SYSTEM_PROMPT = """You are an Etsy digital-product agent. You help the operator design,
create, and manage Excel/Google-Sheets digital downloads for Etsy.

Your core loop:
1. The user describes a product idea (e.g. "restaurant food cost calculator").
2. You call `create_spreadsheet` to design and build the .xlsx file.
3. You call `generate_listing_assets` to create preview images.
4. You call `draft_listing_copy` to produce SEO title/description/tags.
5. You call `create_etsy_draft` to upload everything to Etsy as a DRAFT (never published).
6. The user reviews the draft on etsy.com, then asks you to `publish_listing` once happy.

Rules:
- NEVER call `publish_listing` without explicit user confirmation in the conversation.
- NEVER batch-create more than 5 listings without checking in — Etsy's 2026 algorithm
  penalizes bulk uploaders.
- When designing spreadsheets, lean on the operator's domain expertise. Ask what
  pain point this solves before generating.
- Keep listing titles under 140 chars, max 13 tags, tags 1-20 chars each.
- Prices in USD; default $7-15 for single sheets, $29-49 for bundles.

Be concise. One paragraph max in your text responses unless the user asks for detail."""


# ---------- Tool implementations ----------

@beta_tool
def create_spreadsheet(brief: str) -> str:
    """Design and build an .xlsx spreadsheet from a brief.

    Args:
        brief: Detailed description of what the spreadsheet should do, who it's for,
               and what features it must include. The more specific, the better.
    """
    result = spreadsheet_builder.design_and_build(brief, config.OUTPUT_DIR)
    design = result["design"]

    sheet_summary = ", ".join(s["name"] for s in design["sheets"])
    return json.dumps({
        "title": result["title"],
        "file_path": result["file_path"],
        "sheets": sheet_summary,
        "design": design,
    })


@beta_tool
def generate_listing_assets(
    spreadsheet_title: str,
    niche: str,
    features: list[str],
    callouts: list[dict],
) -> str:
    """Generate two listing preview images (cover + 'what's inside').

    Args:
        spreadsheet_title: The product title to display on the cover.
        niche: Short category label (e.g. "Restaurant Operations").
        features: 3-5 short bullet points highlighting what the buyer gets.
        callouts: List of {heading, body} dicts for the second image — each describes one sheet/feature.
    """
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", spreadsheet_title).strip("_")[:60]
    cover = config.OUTPUT_DIR / f"{safe}_cover.png"
    feature = config.OUTPUT_DIR / f"{safe}_features.png"

    mockup_generator.generate_cover(spreadsheet_title, niche, features, cover)
    mockup_generator.generate_feature_image(
        spreadsheet_title,
        [(c["heading"], c["body"]) for c in callouts],
        feature,
    )
    return json.dumps({"cover": str(cover), "features": str(feature)})


@beta_tool
def draft_listing_copy(
    product_name: str,
    audience: str,
    pain_point: str,
    features: list[str],
) -> str:
    """Generate SEO-optimized Etsy listing copy: title, description, tags.

    Args:
        product_name: The base product name.
        audience: Who buys this (e.g. "independent restaurant owners").
        pain_point: The problem this solves in one sentence.
        features: List of concrete features/benefits.
    """
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    prompt = f"""Write Etsy listing copy for this digital download.

Product: {product_name}
Audience: {audience}
Pain it solves: {pain_point}
Features:
{chr(10).join(f'- {f}' for f in features)}

Return strict JSON only:
{{
  "title": "max 140 chars, front-loaded with the highest-volume keyword phrase",
  "description": "long-form description with sections separated by blank lines, includes what's inside, who it's for, file format note, no-refund disclaimer for digital goods",
  "tags": ["13 tags", "each 1-20 chars", "phrases preferred over single words"],
  "materials": ["spreadsheet", "google sheets", "excel"]
}}"""
    response = client.messages.create(
        model=config.MODEL,
        max_tokens=4000,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    )
    text = next((b.text for b in response.content if b.type == "text"), "")
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    return text


@beta_tool
def create_etsy_draft(
    title: str,
    description: str,
    price: float,
    tags: list[str],
    materials: list[str],
    spreadsheet_file_path: str,
    cover_image_path: str,
    feature_image_path: str,
) -> str:
    """Create a DRAFT listing on Etsy (never auto-published).

    The user must review and publish it manually via etsy.com or by asking
    the agent to call `publish_listing`. Returns the draft listing ID and URL.
    """
    listing = etsy_client.create_draft_listing(
        title=title,
        description=description,
        price=price,
        tags=tags,
        materials=materials,
    )
    listing_id = listing["listing_id"]

    etsy_client.upload_listing_image(listing_id, cover_image_path, rank=1)
    etsy_client.upload_listing_image(listing_id, feature_image_path, rank=2)
    etsy_client.upload_listing_file(listing_id, spreadsheet_file_path, rank=1)

    db.insert_listing(
        spreadsheet_id=0,  # not linking to spreadsheets table from this tool
        etsy_listing_id=listing_id,
        state="draft",
        title=title,
        price_cents=int(round(price * 100)),
    )

    return json.dumps({
        "listing_id": listing_id,
        "state": "draft",
        "edit_url": f"https://www.etsy.com/your/shops/me/tools/listings/{listing_id}",
        "note": "Draft created. Review on Etsy before publishing.",
    })


@beta_tool
def publish_listing(listing_id: int) -> str:
    """Publish a draft listing (set state='active'). Only call after explicit user OK."""
    result = etsy_client.update_listing(listing_id, state="active")
    db.insert_listing(
        spreadsheet_id=0,
        etsy_listing_id=listing_id,
        state="active",
        title=result.get("title", ""),
        price_cents=int(round(float(result.get("price", {}).get("amount", 0))
                              / max(1, int(result.get("price", {}).get("divisor", 100)))
                              * 100)),
    )
    return json.dumps({
        "listing_id": listing_id,
        "state": "active",
        "url": result.get("url"),
    })


@beta_tool
def update_listing(
    listing_id: int,
    title: Optional[str] = None,
    description: Optional[str] = None,
    price: Optional[float] = None,
    tags: Optional[list[str]] = None,
) -> str:
    """Update fields on an existing listing (draft or active)."""
    fields: dict = {}
    if title is not None:
        fields["title"] = title[:140]
    if description is not None:
        fields["description"] = description
    if price is not None:
        fields["price"] = round(float(price), 2)
    if tags is not None:
        fields["tags"] = tags[:13]
    if not fields:
        return json.dumps({"error": "no fields to update"})
    result = etsy_client.update_listing(listing_id, **fields)
    return json.dumps({"listing_id": listing_id, "updated": list(fields.keys())})


@beta_tool
def list_my_listings(state: str = "draft") -> str:
    """List your shop's listings filtered by state.

    Args:
        state: One of 'draft', 'active', 'inactive', 'sold_out', 'expired'.
    """
    listings = etsy_client.list_shop_listings(state=state, limit=50)
    summary = [
        {
            "listing_id": l["listing_id"],
            "title": l["title"],
            "state": l["state"],
            "price": f"{l['price']['amount'] / l['price']['divisor']:.2f} {l['price']['currency_code']}",
            "views": l.get("views"),
            "favorers": l.get("num_favorers"),
        }
        for l in listings
    ]
    return json.dumps(summary)


@beta_tool
def recent_sales(limit: int = 10) -> str:
    """Pull recent sales receipts from Etsy."""
    receipts = etsy_client.get_receipts(limit=limit)
    summary = [
        {
            "receipt_id": r["receipt_id"],
            "buyer_email": r.get("buyer_email"),
            "total": f"{r['grandtotal']['amount'] / r['grandtotal']['divisor']:.2f} {r['grandtotal']['currency_code']}",
            "created_at": r.get("created_timestamp"),
            "is_paid": r.get("is_paid"),
            "is_shipped": r.get("is_shipped"),
        }
        for r in receipts
    ]
    return json.dumps(summary)


TOOLS = [
    create_spreadsheet,
    generate_listing_assets,
    draft_listing_copy,
    create_etsy_draft,
    publish_listing,
    update_listing,
    list_my_listings,
    recent_sales,
]


# ---------- Conversation runner ----------

def run_conversation(user_message: str, history: list[dict] | None = None) -> tuple[str, list[dict]]:
    """Run one user turn. Returns (final_text, updated_history)."""
    db.init()
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    messages = list(history or [])
    messages.append({"role": "user", "content": user_message})

    runner = client.beta.messages.tool_runner(
        model=config.MODEL,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }],
        tools=TOOLS,
        messages=messages,
    )

    final_text_parts: list[str] = []
    last_message = None
    for message in runner:
        last_message = message
        for block in message.content:
            if block.type == "text" and block.text:
                final_text_parts.append(block.text)
            elif block.type == "tool_use":
                print(f"  [tool] {block.name}({_short(block.input)})")

    # Reconstruct history for the next turn — include the final assistant message
    if last_message is not None:
        messages.append({"role": "assistant", "content": last_message.content})

    return "\n".join(final_text_parts).strip(), messages


def _short(obj, length: int = 80) -> str:
    s = json.dumps(obj, default=str)
    return s if len(s) <= length else s[: length - 1] + "…"
