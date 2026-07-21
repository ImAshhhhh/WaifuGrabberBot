"""Bot entry point. Run with: python -m bot

Sets up:
  - Postgres pool
  - Redis client
  - aiogram Dispatcher with all routers
  - Throttling + Activity middlewares
  - Cleanup scheduler (expires old spawns)
  - Long-polling or webhook mode (per USE_WEBHOOK)
"""
from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import settings
from bot.db.pool import init_pool, close_pool
from bot.services.redis_client import init_redis, close_redis
from bot.services.spawn_engine import load_character_cache
from bot.middlewares.throttling import ThrottlingMiddleware
from bot.middlewares.activity import ActivityMiddleware

# Routers
from bot.handlers import start, guess, collection, fav_gift, trade, leaderboards, admin, stats


logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("waifugrabber")


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    # Middlewares: throttle first, then activity tracking
    dp.message.middleware(ThrottlingMiddleware())
    dp.callback_query.middleware(ThrottlingMiddleware())
    dp.message.middleware(ActivityMiddleware())

    # Routers — order matters for command resolution
    dp.include_router(start.router)
    dp.include_router(guess.router)
    dp.include_router(collection.router)
    dp.include_router(fav_gift.router)
    dp.include_router(trade.router)
    dp.include_router(leaderboards.router)
    dp.include_router(admin.router)
    dp.include_router(stats.router)
    return dp


async def cleanup_loop(bot: Bot):
    """Background task: expire spawns that weren't claimed in time."""
    from bot.db.pool import get_pool
    from bot.services.redis_client import get_redis
    import time
    while True:
        try:
            now = int(time.time())
            pool = get_pool()
            async with pool.acquire() as conn:
                expired = await conn.fetch(
                    "SELECT chat_id, message_id FROM active_spawns WHERE expires_at < $1",
                    now,
                )
                for row in expired:
                    try:
                        await bot.edit_message_caption(
                            chat_id=row["chat_id"],
                            message_id=row["message_id"],
                            caption="💨 <i>The character escaped! Nobody claimed her in time.</i>",
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass
                if expired:
                    await conn.execute(
                        "DELETE FROM active_spawns WHERE expires_at < $1", now,
                    )
                    log.info(f"expired {len(expired)} spawns")
        except Exception as e:
            log.warning(f"cleanup loop error: {e}")
        await asyncio.sleep(30)


async def main():
    log.info("Starting WaifuGrabberBot v1.0.0")

    # Init DB + Redis + character cache
    await init_pool()
    log.info("Postgres pool ready")
    await init_redis()
    log.info("Redis ready")
    n_chars = await load_character_cache()
    log.info(f"Loaded {n_chars} characters into memory")

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = build_dispatcher()

    # Background cleanup task
    asyncio.create_task(cleanup_loop(bot))

    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_my_commands([
        ("start", "Welcome + help"),
        ("guess", "Catch a spawned character"),
        ("collection", "View your collection"),
        ("fav", "Set a favorite character"),
        ("gift", "Gift a character (reply to user)"),
        ("trade", "Trade characters (reply to user)"),
        ("topusers", "Global top collectors"),
        ("ctop", "This group's top collectors"),
        ("topgroups", "Global top groups"),
        ("stats", "Your catch stats"),
        ("changetime", "Change spawn interval (admins)"),
    ])

    try:
        if settings.use_webhook:
            from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
            from aiohttp import web

            app = web.Application()
            SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=settings.webhook_path)
            setup_application(app, dp, bot=bot)
            await bot.set_webhook(
                settings.webhook_url,
                secret_token=settings.webhook_secret,
                drop_pending_updates=True,
            )
            log.info(f"Webhook set: {settings.webhook_url}")
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, host=settings.webhook_host, port=settings.webhook_port)
            await site.start()
            log.info(f"Listening on {settings.webhook_host}:{settings.webhook_port}")
            # Block forever
            await asyncio.Event().wait()
        else:
            log.info("Starting long polling...")
            await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await close_pool()
        await close_redis()
        log.info("Shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Stopped by user")
