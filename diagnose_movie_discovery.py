"""READ-ONLY diagnostics for the original Auto_movie_updater-main.

Run on the NEW Render service with its existing environment variables.
Does not post to Telegram, modify Neon, or print secrets.
Temporary Start Command: python -u diagnose_movie_discovery.py && python -u main.py
"""
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import psycopg2
import requests
from dotenv import load_dotenv

load_dotenv()


def say(message):
    print(message, flush=True)


def only_type(error):
    """Avoid request URL/connection strings that could include secrets."""
    code = getattr(error, "pgcode", None)
    return error.__class__.__name__ + (f" (PostgreSQL {code})" if code else "")


def eligibility(release_text, today):
    try:
        release = date.fromisoformat(str(release_text))
    except (ValueError, TypeError):
        return False
    return release <= today or release == today + timedelta(days=7)


def main():
    say("=== MOVIE DISCOVERY AUDIT (READ-ONLY, NO TELEGRAM POST) ===")
    today = datetime.now().date()  # Match original code's clock on Render.
    ist_today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    say(f"[CLOCK] Render process date={today}; India date={ist_today}")

    for name in ("DATABASE_URL", "TMDB_API_KEY"):
        say(f"[ENV] {name}={'SET' if os.getenv(name) else 'MISSING'}")
    if not os.getenv("DATABASE_URL") or not os.getenv("TMDB_API_KEY"):
        say("[STOP] Missing a required environment variable")
        return

    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=8)
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), current_schema(), (SELECT COUNT(*) FROM movie_posts), (SELECT MAX(added_at) FROM movie_posts)")
            db_name, schema, rows, last_insert = cur.fetchone()
            say(f"[RENDER->NEON] database={db_name} schema={schema} rows={rows} newest_added_at={last_insert}")
            cur.execute("""SELECT
                COUNT(*) FILTER (WHERE release_date <= %s AND posted_released = FALSE AND rejected = FALSE),
                COUNT(*) FILTER (WHERE release_date = %s AND posted_7_days = FALSE AND rejected = FALSE)
                FROM movie_posts""", (today, today + timedelta(days=7)))
            pending_released, pending_upcoming = cur.fetchone()
            say(f"[RENDER->NEON] eligible_released={pending_released} eligible_coming_7d={pending_upcoming}")
            cur.execute("SELECT tmdb_id, release_date, posted_7_days, posted_released, rejected FROM movie_posts")
            db_rows = {
                int(row[0]): {"date": row[1], "posted_7": row[2], "posted_released": row[3], "rejected": row[4]}
                for row in cur.fetchall()
            }
    except Exception as error:
        say(f"[RENDER->NEON] CONNECTION/SQL FAILED: {only_type(error)}")
        return
    finally:
        if 'conn' in locals():
            conn.close()

    # This is intentionally the same filter/window as original tmdb_client.py.
    params = {
        "api_key": os.environ["TMDB_API_KEY"],
        "primary_release_date.gte": str(today - timedelta(days=365)),
        "primary_release_date.lte": str(today + timedelta(days=60)),
        "sort_by": "popularity.desc",
        "without_genres": "16",
        "include_adult": "false",
    }
    first_page_eligible_unknown = None
    later_page_eligible_unknown = 0
    seen = set()
    for page in range(1, 6):
        params["page"] = page
        try:
            response = requests.get("https://api.themoviedb.org/3/discover/movie", params=params, timeout=8)
            status = response.status_code
            say(f"[TMDB] page={page} HTTP={status}")
            if status != 200:
                try:
                    detail = response.json()
                    say(f"[TMDB] error status_code={detail.get('status_code', 'N/A')} message={str(detail.get('status_message', ''))[:120]}")
                except ValueError:
                    say("[TMDB] Error body was not JSON")
                say("[CONCLUSION] TMDB request failed on this Render service. Fix API key/network before touching the database.")
                return
            data = response.json()
            results = data.get("results", [])
            if not isinstance(results, list):
                say("[TMDB] Unexpected response: results is not an array")
                return
            distinct = [movie for movie in results if movie.get("id") not in seen]
            seen.update(movie.get("id") for movie in distinct)
            known = [movie for movie in distinct if movie.get("id") in db_rows]
            unknown = [movie for movie in distinct if movie.get("id") not in db_rows]
            eligible_unknown = [movie for movie in unknown if eligibility(movie.get("release_date"), today)]
            known_posted = [movie for movie in known if db_rows[movie["id"]]["posted_released"] is True]
            say(
                f"[TMDB] page={page} returned={len(results)} known_in_neon={len(known)} "
                f"known_already_posted={len(known_posted)} new_to_neon={len(unknown)} "
                f"NEW_ELIGIBLE_TODAY={len(eligible_unknown)}"
            )
            if eligible_unknown:
                examples = ", ".join(f"{str(m.get('title', 'Untitled'))[:36]} ({m.get('release_date')})" for m in eligible_unknown[:3])
                say(f"[TMDB] Example new eligible movies: {examples}")
            if page == 1:
                first_page_eligible_unknown = len(eligible_unknown)
            else:
                later_page_eligible_unknown += len(eligible_unknown)
            total_pages = int(data.get("total_pages") or 0)
            if not results or page >= total_pages:
                break
        except (requests.RequestException, ValueError, TypeError) as error:
            say(f"[TMDB] REQUEST/JSON FAILED: {only_type(error)}")
            say("[CONCLUSION] Check Render-to-TMDB connectivity and configured TMDB_API_KEY")
            return

    say("--- INTERPRETATION ---")
    if first_page_eligible_unknown == 0 and later_page_eligible_unknown > 0:
        say("[CONFIRMED] Page 1 has no newly discovered eligible movies but later pages DO.")
        say("[FIX] tmdb_client.py: fetch multiple discover pages instead of hardcoding page=1.")
    elif first_page_eligible_unknown and first_page_eligible_unknown > 0:
        say("[CHECK] Page 1 has new eligible movies, so the original startup job should insert them.")
        say("[NEXT] Search Render logs for 'Error extracting Movies from TMDB' and verify the deployed commit/code and DATABASE_URL.")
    else:
        say("[CHECK] No NEW eligible movies on first 5 TMDB pages using current filters.")
        say("[NEXT] Broaden discovery window/filters or inspect remaining pages; do not reset posted flags.")
    if rows != 47:
        say(f"[WARNING] This Render database has {rows} rows, but your Neon screenshot showed 47. Check DATABASE_URL branch/database!")
    say("=== END READ-ONLY AUDIT ===")


if __name__ == "__main__":
    main()
