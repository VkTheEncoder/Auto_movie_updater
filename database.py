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

def update_post_status(tmdb_id, column_to_trigger):
    """Marks either the 7-day alert or the final release post as completed."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            query = f"UPDATE movie_posts SET {column_to_trigger} = TRUE WHERE tmdb_id = %s;"
            cur.execute(query, (tmdb_id,))
            conn.commit()

def get_priority_queue(limit=3):
    """
    Executes the selection priority state machine:
    Priority 1: Movies releasing today that haven't had a release post.
    Priority 2: Movies releasing in exactly 7 days that haven't had a warning post.
    """
    today = datetime.now().date()
    seven_days_out = today + timedelta(days=7)
    selected_posts = []

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # 1. Release Day Priority
            cur.execute(
                "SELECT * FROM movie_posts WHERE release_date <= %s AND posted_released = FALSE LIMIT %s;",
                (today, limit)
            )
            selected_posts.extend([{**row, 'type': 'RELEASED'} for row in cur.fetchall()])
            
            # 2. 7 Days Out Priority (If empty slots remain)
            slots_left = limit - len(selected_posts)
            if slots_left > 0:
                cur.execute(
                    "SELECT * FROM movie_posts WHERE release_date = %s AND posted_7_days = FALSE LIMIT %s;",
                    (seven_days_out, slots_left)
                )
                selected_posts.extend([{**row, 'type': 'COMING_SOON'} for row in cur.fetchall()])
                
    return selected_posts
