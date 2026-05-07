"""CLI entry point for the Etsy spreadsheet agent.

Usage:
    python -m etsy_spreadsheet_agent.cli auth          # one-time OAuth setup
    python -m etsy_spreadsheet_agent.cli chat          # interactive chat with the agent
    python -m etsy_spreadsheet_agent.cli listings      # show local DB of created listings
"""

from __future__ import annotations

import sys

from . import agent, config, db
from .tools import etsy_client


def cmd_auth() -> None:
    if not config.ETSY_CLIENT_ID:
        print("Set ETSY_CLIENT_ID in .env first (from etsy.com/developers/your-apps)")
        sys.exit(1)
    tok = etsy_client.authorize_interactive()
    print("✓ Authorized.")
    print(f"  user_id: {config.ETSY_USER_ID or '(check .env)'}")
    print(f"  shop_id: {config.ETSY_SHOP_ID or '(no shop yet — open one on etsy.com)'}")
    print(f"  expires in: {tok['expires_in']}s")


def cmd_listings() -> None:
    db.init()
    rows = db.list_listings()
    if not rows:
        print("(no listings yet)")
        return
    for r in rows:
        price = f"${r['price_cents'] / 100:.2f}" if r["price_cents"] else "?"
        print(f"  [{r['etsy_listing_id']}] {r['state']:7} {price:>8}  {r['title']}")


def cmd_chat() -> None:
    if not config.ANTHROPIC_API_KEY:
        print("Set ANTHROPIC_API_KEY in .env first")
        sys.exit(1)
    if not config.ETSY_ACCESS_TOKEN:
        print("Run `python -m etsy_spreadsheet_agent.cli auth` first")
        sys.exit(1)

    print("Etsy spreadsheet agent. Type 'exit' to quit.\n")
    history: list[dict] = []
    while True:
        try:
            user_input = input("you ▸ ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit", ":q"}:
            break

        try:
            reply, history = agent.run_conversation(user_input, history)
        except Exception as e:
            print(f"  [error] {e}")
            continue
        print(f"\nagent ▸ {reply}\n")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    cmd = sys.argv[1]
    if cmd == "auth":
        cmd_auth()
    elif cmd == "chat":
        cmd_chat()
    elif cmd == "listings":
        cmd_listings()
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
