"""DB initialization + character CSV import.

Run:  python -m bot.db.init_db
"""
import asyncio
import csv
from pathlib import Path

from bot.db.pool import init_pool, close_pool, get_pool
from bot.db.schema import SCHEMA_SQL

CSV_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "waifu_characters.csv"


async def apply_schema(conn) -> None:
    await conn.execute(SCHEMA_SQL)
    print("✓ Schema applied")


async def import_characters(conn) -> int:
    """Replace all characters with the CSV. Idempotent."""
    if not CSV_PATH.exists():
        print(f"✗ CSV not found at {CSV_PATH}")
        return 0

    rows = []
    with open(CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append((
                int(r["id"]),
                r["name"],
                r["anime"],
                r["role"],
                r["rarity"],
                int(r["rarity_score"]),
                int(r["popularity_tier"]),
                r["description"],
                r["aliases"],
                r["image_url"],
            ))

    await conn.execute("TRUNCATE characters RESTART IDENTITY")
    await conn.executemany(
        """
        INSERT INTO characters
          (id, name, anime, role, rarity, rarity_score, popularity_tier, description, aliases, image_url)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
        """,
        rows,
    )
    print(f"✓ Imported {len(rows)} characters")
    return len(rows)


async def main() -> None:
    await init_pool()
    pool = get_pool()
    async with pool.acquire() as conn:
        await apply_schema(conn)
        await import_characters(conn)
    await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
