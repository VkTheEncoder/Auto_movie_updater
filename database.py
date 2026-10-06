import os
from datetime import datetime, timedelta

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")


def get_db_connection():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def is_movie_processed(tmdb_id):
    """Return current tracking flags for one TMDB ID, if present."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT posted_7_days, posted_released, rejected, rejected_reason
                FROM movie_posts
                WHERE tmdb_id = %s;
                """,
                (tmdb_id,),
            )
            return cur.fetchone()


def insert_new_movie(tmdb_id, title, release_date):
    """Insert a newly discovered movie without overwriting existing status flags."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO movie_posts (tmdb_id, title, release_date)
                VALUES (%s, %s, %s)
                ON CONFLICT (tmdb_id) DO NOTHING;
                """,
                (tmdb_id, title, release_date),
            )
            conn.commit()


def update_post_status(tmdb_id, column_to_trigger):
    """Mark a successful Telegram post as completed."""
    allowed_columns = {"posted_7_days", "posted_released"}
    if column_to_trigger not in allowed_columns:
        raise ValueError(f"Invalid post status column: {column_to_trigger}")

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            query = f"UPDATE movie_posts SET {column_to_trigger} = TRUE WHERE tmdb_id = %s;"
            cur.execute(query, (tmdb_id,))
            conn.commit()


def reject_movie(tmdb_id, reason):
    """Mark an invalid candidate as rejected without pretending it was posted."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE movie_posts
                SET rejected = TRUE,
                    rejected_reason = %s
                WHERE tmdb_id = %s;
                """,
                (reason, tmdb_id),
            )
            conn.commit()


def get_priority_queue(limit=1):
    """
    Priority 1: releases exactly 7 days from today.
    Priority 2: releases today.
    Priority 3: older released movies, newest first.

    Rejected rows are excluded from every queue.
    """
    today = datetime.now().date()
    seven_days_out = today + timedelta(days=7)
    selected_posts = []

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM movie_posts
                WHERE release_date = %s
                  AND posted_7_days = FALSE
                  AND rejected = FALSE
                ORDER BY release_date DESC
                LIMIT %s;
                """,
                (seven_days_out, limit),
            )
            selected_posts.extend(
                [{**row, "type": "COMING_SOON"} for row in cur.fetchall()]
            )

            if len(selected_posts) >= limit:
                return selected_posts[:limit]

            slots_left = limit - len(selected_posts)
            cur.execute(
                """
                SELECT *
                FROM movie_posts
                WHERE release_date = %s
                  AND posted_released = FALSE
                  AND rejected = FALSE
                ORDER BY release_date DESC
                LIMIT %s;
                """,
                (today, slots_left),
            )
            selected_posts.extend(
                [{**row, "type": "RELEASED"} for row in cur.fetchall()]
            )

            if len(selected_posts) >= limit:
                return selected_posts[:limit]

            slots_left = limit - len(selected_posts)
            cur.execute(
                """
                SELECT *
                FROM movie_posts
                WHERE release_date < %s
                  AND posted_released = FALSE
                  AND rejected = FALSE
                ORDER BY release_date DESC
                LIMIT %s;
                """,
                (today, slots_left),
            )
            selected_posts.extend(
                [{**row, "type": "RELEASED"} for row in cur.fetchall()]
            )

    return selected_posts
