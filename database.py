import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def is_movie_processed(tmdb_id):
    """Checks if a movie completely exists in the tracking database."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT posted_7_days, posted_released FROM movie_posts WHERE tmdb_id = %s;", (tmdb_id,))
            return cur.fetchone()

def insert_new_movie(tmdb_id, title, release_date):
    """Inserts a freshly discovered upcoming or recent movie."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO movie_posts (tmdb_id, title, release_date)
                VALUES (%s, %s, %s) ON CONFLICT (tmdb_id) DO NOTHING;
                """,
                (tmdb_id, title, release_date)
            )
            conn.commit()

def reject_movie(tmdb_id, reason):
    """Marks an invalid candidate separately from an actually posted movie."""

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE movie_posts
                SET rejected = TRUE,
                    rejected_reason = %s
                WHERE tmdb_id = %s;
                """,
                (reason, tmdb_id)
            )

            conn.commit()

def get_priority_queue(limit=1):
    """
    Executes the selection priority state machine:
    Priority 1: Movies releasing in exactly 7 days.
    Priority 2: Movies releasing today.
    Priority 3: Older released movies, sorted descending (newest first).
    """
    today = datetime.now().date()
    seven_days_out = today + timedelta(days=7)
    selected_posts = []

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # 1. 7 Days Out Priority (Highest)
            cur.execute(
                "SELECT * FROM movie_posts WHERE release_date = %s AND posted_7_days = FALSE AND rejected = FALSE LIMIT %s;",
                (seven_days_out, limit)
            )
            selected_posts.extend([{**row, 'type': 'COMING_SOON'} for row in cur.fetchall()])
            
            if len(selected_posts) == limit: 
                return selected_posts

            # 2. Release Day Priority
            slots_left = limit - len(selected_posts)
            cur.execute(
                "SELECT * FROM movie_posts WHERE release_date = %s AND posted_released = FALSE AND rejected = FALSE LIMIT %s;",
                (today, slots_left)
            )
            selected_posts.extend([{**row, 'type': 'RELEASED'} for row in cur.fetchall()])
            
            if len(selected_posts) == limit: 
                return selected_posts

            # 3. Fallback: Old movies not yet posted (Descending Order)
            slots_left = limit - len(selected_posts)
            cur.execute(
                """
                SELECT * FROM movie_posts 
                WHERE release_date < %s
                AND posted_released = FALSE
                AND rejected = FALSE
                ORDER BY release_date DESC 
                LIMIT %s;
                """,
                (today, slots_left)
            )
            selected_posts.extend([{**row, 'type': 'RELEASED'} for row in cur.fetchall()])
                
    return selected_posts
