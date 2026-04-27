import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

SCHEMA = """
CREATE TABLE IF NOT EXISTS social_media_user (
    id UUID PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    full_name VARCHAR(255),
    hobbies TEXT,
    address TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS social_media_profile (
    id SERIAL PRIMARY KEY,
    user_id UUID REFERENCES social_media_user(id) ON DELETE CASCADE,
    bio TEXT,
    education TEXT,
    occupation TEXT,
    avatar VARCHAR(255),
    UNIQUE(user_id)
);

CREATE TABLE IF NOT EXISTS social_media_category (
    id UUID PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS social_media_profile_interests (
    id SERIAL PRIMARY KEY,
    profile_id INT REFERENCES social_media_profile(id) ON DELETE CASCADE,
    category_id UUID REFERENCES social_media_category(id) ON DELETE CASCADE,
    UNIQUE(profile_id, category_id)
);

CREATE TABLE IF NOT EXISTS social_media_user_following (
    id SERIAL PRIMARY KEY,
    from_user_id UUID REFERENCES social_media_user(id) ON DELETE CASCADE,
    to_user_id UUID REFERENCES social_media_user(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(from_user_id, to_user_id)
);

CREATE TABLE IF NOT EXISTS social_media_user_blocked_users (
    id SERIAL PRIMARY KEY,
    from_user_id UUID REFERENCES social_media_user(id) ON DELETE CASCADE,
    to_user_id UUID REFERENCES social_media_user(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(from_user_id, to_user_id)
);

CREATE TABLE IF NOT EXISTS social_media_post (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES social_media_user(id) ON DELETE CASCADE,
    content TEXT,
    views_count INT DEFAULT 0,
    shared_post_id UUID REFERENCES social_media_post(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS social_media_postmedia (
    id UUID PRIMARY KEY,
    post_id UUID REFERENCES social_media_post(id) ON DELETE CASCADE,
    file VARCHAR(255),
    media_type VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS social_media_post_categories (
    id SERIAL PRIMARY KEY,
    post_id UUID REFERENCES social_media_post(id) ON DELETE CASCADE,
    category_id UUID REFERENCES social_media_category(id) ON DELETE CASCADE,
    UNIQUE(post_id, category_id)
);

CREATE TABLE IF NOT EXISTS social_media_reaction (
    id SERIAL PRIMARY KEY,
    user_id UUID REFERENCES social_media_user(id) ON DELETE CASCADE,
    post_id UUID REFERENCES social_media_post(id) ON DELETE CASCADE,
    type VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, post_id)
);

CREATE TABLE IF NOT EXISTS social_media_comment (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES social_media_user(id) ON DELETE CASCADE,
    post_id UUID REFERENCES social_media_post(id) ON DELETE CASCADE,
    parent_id UUID REFERENCES social_media_comment(id) ON DELETE CASCADE,
    content TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
"""

def init_db():
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", 5436),
            dbname=os.getenv("DB_NAME", "social_db"),
            user=os.getenv("DB_USER", "innovator_user"),
            password=os.getenv("DB_PASSWORD", "Nep@tronix9335%")
        )
        conn.autocommit = True
        cur = conn.cursor()
        
        print("Initializing schema...")
        cur.execute(SCHEMA)
        print("Schema initialized successfully.")
        
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error initializing DB: {e}")

if __name__ == "__main__":
    init_db()

