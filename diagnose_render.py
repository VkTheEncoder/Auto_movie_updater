"""Read-only diagnostics for Auto_movie_updater-main (Render / Neon / TMDB / Telegram).

Safe to run alongside the original repository. Never posts messages or changes rows.
Run once: python -u diagnose_render.py
To run before your normal web service: python -u diagnose_render.py && python -u main.py
"""
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import psycopg2
import requests
from dotenv import load_dotenv

load_dotenv()
TIMEOUT = 12
TODAY = datetime.now(ZoneInfo("Asia/Kolkata")).date()


def log(message):
    print(message, flush=True)


def read_error(error):
    # Never print request URLs, because the Telegram bot token is embedded in them.
    if isinstance(error, requests.exceptions.RequestException):
        return type(error).__name__
    if isinstance(error, psycopg2.Error):
        return f"{type(error).__name__} (pgcode={getattr(error, 'pgcode', None) or 'none'})"
    return type(error).__name__


def postgres_check():
    log("\n[NEON] Starting read-only PostgreSQL checks")
    url = os.getenv("DATABASE_URL")
    if not url:
        log("[NEON] ERROR: DATABASE_URL missing")
        return
    try:
        with psycopg2.connect(url, connect_timeout=TIMEOUT) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT current_database(), current_user, current_schema(), to_regclass('movie_posts')")
                name, user, schema, table = cur.fetchone()
                log(f"[NEON] Connected: database={name}, role={user}, schema={schema}, movie_posts_exists={table is not None}")
                if table is None:
                    log("[NEON] ERROR: movie_posts table not found in the connected database/branch")
                    return
                cur.execute("""SELECT column_name FROM information_schema.columns
                    WHERE table_schema = ANY (current_schemas(false)) AND table_name = 'movie_posts'""")
                columns = {row[0] for row in cur.fetchall()}
                expected = {"tmdb_id", "title", "release_date", "posted_7_days", "posted_released", "rejected", "rejected_reason"}
                missing = sorted(expected - columns)
                log(f"[NEON] Required columns missing: {missing if missing else 'NONE'}")
                if missing:
                    return
                cur.execute("""SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE posted_released IS TRUE) AS released_posted,
                    COUNT(*) FILTER (WHERE rejected IS TRUE) AS rejected,
                    COUNT(*) FILTER (WHERE posted_released IS FALSE AND rejected IS FALSE AND release_date <= %s) AS released_pending,
                    COUNT(*) FILTER (WHERE posted_7_days IS FALSE AND rejected IS FALSE AND release_date = %s) AS coming_soon_pending
                    FROM movie_posts""", (TODAY, TODAY + timedelta(days=7)))
                total, posted, rejected, pending_released, pending_soon = cur.fetchone()
                log(f"[NEON] rows={total}, posted_released={posted}, rejected={rejected}, releasable_pending={pending_released}, coming_7d_pending={pending_soon}")
                cur.execute("""SELECT tmdb_id, release_date, posted_7_days, posted_released, rejected
                    FROM movie_posts
                    WHERE (release_date = %s AND posted_7_days IS FALSE AND rejected IS FALSE)
                      OR (release_date <= %s AND posted_released IS FALSE AND rejected IS FALSE)
                    ORDER BY CASE WHEN release_date = %s THEN 0 ELSE 1 END, release_date DESC LIMIT 3""",
                            (TODAY + timedelta(days=7), TODAY, TODAY + timedelta(days=7)))
                sample = cur.fetchall()
                log(f"[NEON] Queue sample (ID, release date, 7d posted, released posted, rejected): {sample}")
    except Exception as err:
        log(f"[NEON] ERROR: {read_error(err)}")


def tmdb_check():
    log("\n[TMDB] Checking exact discover request used by your bot")
    key = os.getenv("TMDB_API_KEY")
    if not key:
        log("[TMDB] ERROR: TMDB_API_KEY missing")
        return
    params = {
        "api_key": key,
        "primary_release_date.gte": str(TODAY - timedelta(days=365)),
        "primary_release_date.lte": str(TODAY + timedelta(days=60)),
        "sort_by": "popularity.desc",
        "without_genres": "16",
        "include_adult": "false",
        "page": 1,
    }
    try:
        res = requests.get("https://api.themoviedb.org/3/discover/movie", params=params, timeout=TIMEOUT)
        data = res.json() if "json" in res.headers.get("content-type", "").lower() else {}
        count = len(data.get("results", [])) if isinstance(data, dict) else 0
        log(f"[TMDB] HTTP={res.status_code}, first_page_movie_count={count}")
        if res.status_code != 200:
            log(f"[TMDB] API error status_code={data.get('status_code', 'unknown') if isinstance(data, dict) else 'unknown'}")
    except Exception as err:
        log(f"[TMDB] ERROR: {read_error(err)}")


def telegram_call(token, endpoint, params=None):
    try:
        response = requests.get(f"https://api.telegram.org/bot{token}/{endpoint}", params=params, timeout=TIMEOUT)
        data = response.json()
        if not data.get("ok"):
            log(f"[TELEGRAM] {endpoint} failed: HTTP={response.status_code}, {data.get('description', 'unknown')}" )
        return data.get("result") if data.get("ok") else None
    except Exception as err:
        log(f"[TELEGRAM] {endpoint} ERROR: {read_error(err)}")
        return None


def telegram_check():
    log("\n[TELEGRAM] Read-only token and channel checks; no messages sent")
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    channel = os.getenv("TELEGRAM_CHANNEL_ID")
    if not token or not channel:
        log("[TELEGRAM] ERROR: missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHANNEL_ID")
        return
    bot = telegram_call(token, "getMe")
    if not bot:
        return
    log(f"[TELEGRAM] Bot token valid; bot_username=@{bot.get('username')}")
    chat = telegram_call(token, "getChat", {"chat_id": channel})
    if not chat:
        return
    log(f"[TELEGRAM] Target chat type={chat.get('type')}, title={chat.get('title', '(no title)')}, ID={chat.get('id')}")
    member = telegram_call(token, "getChatMember", {"chat_id": channel, "user_id": bot.get("id")})
    if member:
        status = member.get("status")
        can_post = member.get("can_post_messages", "unspecified")
        log(f"[TELEGRAM] Bot membership={status}; can_post_messages={can_post}")
        if chat.get('type') == 'channel' and status not in ('administrator', 'creator'):
            log('[TELEGRAM] WARNING: bot is not a channel administrator')
        if chat.get('type') == 'channel' and status == 'administrator' and can_post is False:
            log('[TELEGRAM] ERROR: bot cannot post messages to the channel')


def main():
    log("=== Auto Movie Updater: account-migration diagnostic (NO POSTING / NO DATABASE CHANGES) ===")
    log(f"Date IST: {TODAY}")
    for key in ("DATABASE_URL", "TMDB_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHANNEL_ID"):
        log(f"[ENV] {key}: {'PRESENT' if os.getenv(key) else 'MISSING'}")
    postgres_check()
    tmdb_check()
    telegram_check()
    log("\n=== Diagnostic complete; do not share actual environment variable values ===")


if __name__ == "__main__":
    main()
