CREATE TABLE IF NOT EXISTS movie_posts (
    tmdb_id INT PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    release_date DATE NOT NULL,
    posted_7_days BOOLEAN DEFAULT FALSE,
    posted_released BOOLEAN DEFAULT FALSE,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
