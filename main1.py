# """
# main.py  Post Recommendation Score Generator + FastAPI
# --------------------------------------------------------
# Inputs:
#   - data/post_random_scores.csv
#   - data/post_trending_scores.csv
#   - score/content_score.py  (FAISS-based, run as subprocess)

# Run API server:
#   uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Run CLI:
#   python main.py <user_id>

# API Endpoints:
#   GET  /recommend/{user_id}
#   GET  /recommend/{user_id}?top_n=10
#   GET  /health
# """

# import sys
# import os
# import subprocess
# import json
# import pandas as pd
# import numpy as np
# from typing import List, Optional, Any
# import psycopg2
# import psycopg2.extras
# from fastapi import FastAPI, HTTPException, Query
# from fastapi.middleware.cors import CORSMiddleware
# from pydantic import BaseModel
# from concurrent.futures import ThreadPoolExecutor
# from apscheduler.schedulers.background import BackgroundScheduler
# from dotenv import load_dotenv




# from score.random_score import generate_random_scores as refresh_random_scores
# from score.content_score import search_posts_for_user as search_posts_for_user
# from score.collaborative_score import collaborative_filter_response as collaborative_filter_response

# load_dotenv()
# DB_CONFIG = {
#     "host": os.getenv("DB_HOST"),
#     "port": int(os.getenv("DB_PORT")),
#     "dbname": os.getenv("DB_NAME"),
#     "user": os.getenv("DB_USER"),
#     "password": os.getenv("DB_PASSWORD")
# }
# MEDIA_BASE_URL = "http://36.253.137.34:8005"   # prepended to avatar paths


# def get_db_connection():
#     return psycopg2.connect(**DB_CONFIG)


# # CONFIG

# TRENDING_SCORES_CSV = "data/post_trending_scores.csv"


# WEIGHTS = {
#     "content_score":  0.30,
#     "trending_score": 0.20,
#     "random_score":   0.10,
#     "collaborative_score": 0.40,
# }

# TOP_N      = 10
# OUTPUT_CSV = False





# # FASTAPI APP
# app = FastAPI(
#     title="Social Media Recommendation API",
#     version="3.0.0",
# )

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_methods=["*"],
#     allow_headers=["*"],
# )


# # RESPONSE MODELS  (matching exact response shape)
# class MediaItem(BaseModel):
#     id:         str
#     file:       str
#     media_type: str


# class CommentItem(BaseModel):
#     id:         str
#     username:   str
#     avatar:     Optional[str]
#     post:       str
#     parent:     Optional[str]
#     content:    str
#     created_at: str


# class SharedPostDetails(BaseModel):
#     id:         str
#     username:   str
#     full_name:  Optional[str]
#     avatar:     Optional[str]
#     content:    Optional[str]
#     created_at: str
#     media:      List[MediaItem]


# class PostDetail(BaseModel):
#     id:                    str
#     user_id:               str
#     username:              str
#     avatar:                Optional[str]
#     content:               Optional[str]
#     media:                 List[MediaItem]
#     categories_detail:     List[Any]
#     shared_post:           Optional[str]
#     shared_post_details:   Optional[SharedPostDetails]
#     reactions_count:       int
#     like_count:            int
#     reaction_types:        List[str]
#     current_user_reaction: Optional[str]
#     is_followed:           bool
#     comments_count:        int
#     comments:              List[CommentItem]
#     views_count:           int
#     created_at:            str
#     updated_at:            str
#     # scoring
#     final_score:           float
#     content_score:         float
#     trending_score:        float
#     random_score:          float


# class RecommendationResponse(BaseModel):
#     user_id:     str
#     total_posts: int
#     top_n:       int
#     posts:       List[PostDetail]


# # AVATAR HELPER
# def full_avatar_url(path: Optional[str]) -> Optional[str]:
#     if not path:
#         return None
#     if path.startswith("http"):
#         return path
#     return f"{MEDIA_BASE_URL}/media/{path.lstrip('/')}"


# def full_media_url(path: Optional[str]) -> Optional[str]:
#     if not path:
#         return None
#     if path.startswith("http"):
#         return path
#     return f"{MEDIA_BASE_URL}/media/{path.lstrip('/')}"


# # DB STEP 1  Validate user_id exists
# def validate_user_in_db(user_id: str) -> dict:
#     conn = get_db_connection()
#     try:
#         with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
#             cur.execute(
#                 """
#                 SELECT u.id::text   AS id,
#                        u.username,
#                        u.full_name,
#                        p.avatar
#                 FROM   social_media_user    u
#                 LEFT   JOIN social_media_profile p ON p.user_id = u.id
#                 WHERE  u.id = %s::uuid
#                 """,
#                 (user_id,),
#             )
#             row = cur.fetchone()
#             if not row:
#                 raise ValueError(
#                     f"User '{user_id}' does not exist in the database."
#                 )
#             return dict(row)
#     finally:
#         conn.close()


# # DB STEP 2  Cross-check post_ids against DB
# def filter_posts_existing_in_db(post_ids: List[str]) -> List[str]:
#     if not post_ids:
#         return []
#     conn = get_db_connection()
#     try:
#         with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
#             cur.execute(
#                 "SELECT id::text FROM social_media_post WHERE id = ANY(%s::uuid[])",
#                 (post_ids,),
#             )
#             existing = {row["id"] for row in cur.fetchall()}
#     finally:
#         conn.close()
#     return [pid for pid in post_ids if pid in existing]


# # DB ENRICHMENT HELPERS
# def _fetch_post_media(cur, post_ids: List[str]) -> dict:
#     if not post_ids:
#         return {pid: [] for pid in post_ids}
#     cur.execute(
#         """
#         SELECT id::text, post_id::text, file, media_type
#         FROM   social_media_postmedia
#         WHERE  post_id = ANY(%s::uuid[])
#         """,
#         (post_ids,),
#     )
#     result: dict = {pid: [] for pid in post_ids}
#     for row in cur.fetchall():
#         result[row["post_id"]].append(
#             MediaItem(id=row["id"],
#                       file=full_media_url(row["file"]),
#                       media_type=row["media_type"])
#         )
#     return result


# def _fetch_post_categories(cur, post_ids: List[str]) -> dict:
#     if not post_ids:
#         return {pid: [] for pid in post_ids}
#     cur.execute(
#         """
#         SELECT pc.post_id::text,
#                c.id::text  AS cat_id,
#                c.name      AS cat_name
#         FROM   social_media_post_categories pc
#         JOIN   social_media_category        c  ON c.id = pc.category_id
#         WHERE  pc.post_id = ANY(%s::uuid[])
#         """,
#         (post_ids,),
#     )
#     result: dict = {pid: [] for pid in post_ids}
#     for row in cur.fetchall():
#         result[row["post_id"]].append(
#             {"id": row["cat_id"], "name": row["cat_name"]}
#         )
#     return result


# def _fetch_reactions(cur, post_ids: List[str]) -> dict:
#     if not post_ids:
#         return {pid: {"reactions_count": 0, "like_count": 0, "reaction_types": []} for pid in post_ids}
#     cur.execute(
#         """
#         SELECT post_id::text,
#                type        AS reaction_type,
#                COUNT(*)    AS cnt
#         FROM   social_media_reaction
#         WHERE  post_id = ANY(%s::uuid[])
#         GROUP  BY post_id, type
#         """,
#         (post_ids,),
#     )
#     result: dict = {
#         pid: {"reactions_count": 0, "like_count": 0, "reaction_types": []}
#         for pid in post_ids
#     }
#     for row in cur.fetchall():
#         pid   = row["post_id"]
#         rtype = row["reaction_type"]
#         cnt   = row["cnt"]
#         result[pid]["reactions_count"] += cnt
#         if rtype not in result[pid]["reaction_types"]:
#             result[pid]["reaction_types"].append(rtype)
#         if rtype == "like":
#             result[pid]["like_count"] += cnt
#     return result


# def _fetch_comments(cur, post_ids: List[str]) -> dict:
#     if not post_ids:
#         return {pid: [] for pid in post_ids}
#     cur.execute(
#         """
#         SELECT c.id::text,
#                c.post_id::text,
#                c.parent_id::text  AS parent,
#                c.content,
#                c.created_at::text,
#                u.username,
#                p.avatar
#         FROM   social_media_comment  c
#         JOIN   social_media_user     u ON u.id = c.user_id
#         LEFT   JOIN social_media_profile p ON p.user_id = c.user_id
#         WHERE  c.post_id = ANY(%s::uuid[])
#         ORDER  BY c.created_at DESC
#         """,
#         (post_ids,),
#     )
#     result: dict = {pid: [] for pid in post_ids}
#     counts: dict = {pid: 0 for pid in post_ids}
#     for row in cur.fetchall():
#         pid = row["post_id"]
#         if counts[pid] >= 10:
#             continue
#         result[pid].append(
#             CommentItem(
#                 id         = row["id"],
#                 username   = row["username"],
#                 avatar     = row["avatar"],
#                 post       = row["post_id"],
#                 parent     = row["parent"],
#                 content    = row["content"],
#                 created_at = row["created_at"],
#             )
#         )
#         counts[pid] += 1
#     return result


# def _fetch_comments_count(cur, post_ids: List[str]) -> dict:
#     if not post_ids:
#         return {pid: 0 for pid in post_ids}
#     cur.execute(
#         """
#         SELECT post_id::text, COUNT(*) AS cnt
#         FROM   social_media_comment
#         WHERE  post_id = ANY(%s::uuid[])
#         GROUP  BY post_id
#         """,
#         (post_ids,),
#     )
#     result = {pid: 0 for pid in post_ids}
#     for row in cur.fetchall():
#         result[row["post_id"]] = row["cnt"]
#     return result


# def _fetch_shared_post_details(cur, shared_ids: List[str]) -> dict:
#     ids = [pid for pid in shared_ids if pid]
#     if not ids:
#         return {}
#     cur.execute(
#         """
#         SELECT p.id::text,
#                p.content,
#                p.created_at::text,
#                u.username,
#                u.full_name,
#                pr.avatar
#         FROM   social_media_post    p
#         JOIN   social_media_user    u  ON u.id = p.user_id
#         LEFT   JOIN social_media_profile pr ON pr.user_id = p.user_id
#         WHERE  p.id = ANY(%s::uuid[])
#         """,
#         (ids,),
#     )
#     rows  = {row["id"]: dict(row) for row in cur.fetchall()}
#     media = _fetch_post_media(cur, ids)

#     result = {}
#     for pid, row in rows.items():
#         result[pid] = SharedPostDetails(
#             id         = pid,
#             username   = row["username"],
#             full_name  = row["full_name"] or None,
#             avatar     = full_avatar_url(row["avatar"]),
#             content    = row["content"],
#             created_at = row["created_at"],
#             media      = media.get(pid, []),
#         )
#     return result


# def _is_followed(cur, requesting_user_id: str, owner_ids: List[str]) -> dict:
#     if not owner_ids or not requesting_user_id:
#         return {uid: False for uid in owner_ids}
#     cur.execute(
#         """
#         SELECT to_user_id::text
#         FROM   social_media_user_following
#         WHERE  from_user_id = %s::uuid
#           AND  to_user_id   = ANY(%s::uuid[])
#         """,
#         (requesting_user_id, owner_ids),
#     )
#     followed = {row["to_user_id"] for row in cur.fetchall()}
#     return {uid: (uid in followed) for uid in owner_ids}


# def _current_user_reaction(cur, requesting_user_id: str, post_ids: List[str]) -> dict:
#     if not post_ids or not requesting_user_id:
#         return {pid: None for pid in post_ids}
#     cur.execute(
#         """
#         SELECT post_id::text, type AS reaction_type
#         FROM   social_media_reaction
#         WHERE  user_id = %s::uuid
#           AND  post_id = ANY(%s::uuid[])
#         """,
#         (requesting_user_id, post_ids),
#     )
#     result = {pid: None for pid in post_ids}
#     for row in cur.fetchall():
#         result[row["post_id"]] = row["reaction_type"]
#     return result


# # DB STEP 3  Fetch full enriched post details
# def fetch_post_details(post_ids: List[str], requesting_user_id: str) -> dict:
#     if not post_ids:
#         return {}

#     conn = get_db_connection()
#     try:
#         with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
#             cur.execute(
#                 """
#                 SELECT p.id::text,
#                        p.content,
#                        p.created_at::text,
#                        p.updated_at::text,
#                        p.shared_post_id::text  AS shared_post,
#                        p.views_count,
#                        u.id::text              AS user_id,
#                        u.username,
#                        u.full_name,
#                        pr.avatar
#                 FROM   social_media_post     p
#                 JOIN   social_media_user     u  ON u.id = p.user_id
#                 LEFT   JOIN social_media_profile pr ON pr.user_id = p.user_id
#                 WHERE  p.id = ANY(%s::uuid[])
#                 """,
#                 (post_ids,),
#             )
#             posts_raw = {row["id"]: dict(row) for row in cur.fetchall()}

#             if not posts_raw:
#                 return {}

#             found_ids  = list(posts_raw.keys())
#             owner_ids  = list({r["user_id"] for r in posts_raw.values()})
#             shared_ids = [r["shared_post"] for r in posts_raw.values() if r.get("shared_post")]

#             media_map        = _fetch_post_media(cur, found_ids)
#             category_map     = _fetch_post_categories(cur, found_ids)
#             reaction_map     = _fetch_reactions(cur, found_ids)
#             comment_map      = _fetch_comments(cur, found_ids)
#             comment_cnt_map  = _fetch_comments_count(cur, found_ids)
#             shared_map       = _fetch_shared_post_details(cur, shared_ids)
#             follow_map       = _is_followed(cur, requesting_user_id, owner_ids)
#             cur_reaction_map = _current_user_reaction(cur, requesting_user_id, found_ids)

#             result = {}
#             for pid, row in posts_raw.items():
#                 rxn = reaction_map.get(pid, {})
#                 result[pid] = {
#                     "id":                    pid,
#                     "user_id":               row["user_id"],
#                     "username":              row["username"],
#                     "avatar":                full_avatar_url(row["avatar"]),
#                     "content":               row["content"],
#                     "media":                 media_map.get(pid, []),
#                     "categories_detail":     category_map.get(pid, []),
#                     "shared_post":           row.get("shared_post"),
#                     "shared_post_details":   shared_map.get(row.get("shared_post")),
#                     "reactions_count":       rxn.get("reactions_count", 0),
#                     "like_count":            rxn.get("like_count", 0),
#                     "reaction_types":        rxn.get("reaction_types", []),
#                     "current_user_reaction": cur_reaction_map.get(pid),
#                     "is_followed":           follow_map.get(row["user_id"], False),
#                     "comments_count":        comment_cnt_map.get(pid, 0),
#                     "comments":              comment_map.get(pid, []),
#                     "views_count":           row["views_count"] or 0,
#                     "created_at":            row["created_at"],
#                     "updated_at":            row["updated_at"],
#                 }
#             return result
#     finally:
#         conn.close()


# # CONTENT SCORER SUBPROCESS

# def get_content_scores(user_id: str) -> pd.DataFrame:
#     try:
#         results = search_posts_for_user(user_id)
#     except ValueError as e:
#         raise RuntimeError(f"Content scorer failed for user '{user_id}': {e}")

#     df = pd.DataFrame(results).rename(columns={"similarity": "content_score"})
#     df["post_id"] = df["post_id"].astype(str)
#     return df
# def get_collaborative_scores(user_id: str) -> pd.DataFrame:
#     try:
#         results = collaborative_filter_response(user_id)
#     except ValueError as e:
#         raise RuntimeError(f"Collaborative scorer failed for user '{user_id}': {e}")

#     # Guard: if no results returned, return empty DataFrame with correct columns
#     if not results:
#         return pd.DataFrame(columns=["post_id", "collaborative_score"])

#     df = pd.DataFrame(results)  # results = [{"post_id": ..., "similarity": ...}, ...]

#     # Guard: check expected keys exist
#     if "post_id" not in df.columns or "similarity" not in df.columns:
#         return pd.DataFrame(columns=["post_id", "collaborative_score"])

#     df = df.rename(columns={"similarity": "collaborative_score"})
#     df["post_id"] = df["post_id"].astype(str)
#     return df

# # DATA LOADERS
# def load_random_scores() -> pd.DataFrame:
#     data = refresh_random_scores()
#     df = pd.DataFrame(data) if isinstance(data, list) else data
#     df["post_id"] = df["post_id"].astype(str)
#     return df


# def load_trending_scores() -> pd.DataFrame:
#     cols = [
#         "post_id", "trending_score", "views", "total_reactions",
#         "like_count", "love_count", "haha_count", "wow_count",
#         "sad_count", "angry_count", "comment_count", "created_at",
#     ]
#     df = pd.read_csv(TRENDING_SCORES_CSV)
#     existing = [c for c in cols if c in df.columns]
#     df = df[existing].drop_duplicates("post_id")
#     df["post_id"] = df["post_id"].astype(str)
#     return df


# def min_max_normalize(series: pd.Series) -> pd.Series:
#     lo, hi = series.min(), series.max()
#     if hi == lo:
#         return pd.Series(np.zeros(len(series)), index=series.index)
#     return (series - lo) / (hi - lo)


# # CORE SCORING PIPELINE
# def get_recommendations(user_id: str, top_n: int = TOP_N, save_csv: bool = OUTPUT_CSV) -> pd.DataFrame:
#     print(f"\n Scoring for user_id: {user_id}")

#     df_random   = load_random_scores()
#     df_trending = load_trending_scores()
#     df          = pd.merge(df_random, df_trending, on="post_id", how="inner")
#     print(f"   CSV dataset: {len(df)} posts")

#     df_content = get_content_scores(user_id)
#     print(f"   Content model: {len(df_content)} posts scored")

#     df_collaborative = get_collaborative_scores(user_id)
#     print(f"   Collaborative model: {len(df_collaborative)} posts scored")

#     df = pd.merge(df, df_content, on="post_id", how="left")
#     df["content_score"] = df["content_score"].fillna(0.0)
    
#     df = pd.merge(df, df_collaborative, on="post_id", how="left")
#     df["collaborative_score"] = df["collaborative_score"].fillna(0.0)

#     df["random_score_norm"]   = min_max_normalize(df["random_score"])
#     df["trending_score_norm"] = min_max_normalize(df["trending_score"])
#     df["content_score_norm"]  = min_max_normalize(df["content_score"])
#     df["collaborative_score_norm"] = min_max_normalize(df["collaborative_score"])

#     df["final_score"] = (
#         WEIGHTS["content_score"]  * df["content_score_norm"]  +
#         WEIGHTS["trending_score"] * df["trending_score_norm"] +
#         WEIGHTS["random_score"]   * df["random_score_norm"] +
#         WEIGHTS["collaborative_score"] * df["collaborative_score_norm"]
#     )

#     df = df.sort_values("final_score", ascending=False).reset_index(drop=True)
#     df.index += 1

#     base_cols  = ["post_id", "final_score", "content_score", "trending_score", "random_score"]
#     extra_cols = ["views", "total_reactions", "comment_count", "created_at"]
#     out_cols   = base_cols + [c for c in extra_cols if c in df.columns]

#     result = df[out_cols].head(top_n * 3)
#     for col in ["final_score", "content_score", "trending_score", "random_score"]:
#         if col in result.columns:
#             result[col] = result[col].round(4)

#     if save_csv:
#         out_file = f"recommended_posts_{user_id}.csv"
#         result.to_csv(out_file)
#         print(f"   Saved  {out_file}")

#     return result


# # API ENDPOINTS
# @app.get("/health", tags=["Health"])
# def health_check():
#     return {"status": "ok", "message": "Recommendation API is running."}


# @app.get(
#     "/recommend/{user_id}",
#     response_model=RecommendationResponse,
#     tags=["Recommendations"],
#     summary="Get post recommendations for a user",
# )
# def recommend(
#     user_id: str,
#     top_n: int = Query(default=TOP_N, ge=1, le=100, description="Number of posts to return"),
# ):
   
   
#     # Step 1  Validate user
#     try:
#         validate_user_in_db(user_id)
#     except ValueError as e:
#         raise HTTPException(status_code=404, detail=str(e))
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"user is not found in database: {e}")

#     # Step 2  Score
#     try:
#         df = get_recommendations(user_id, top_n=top_n, save_csv=False)
#     except RuntimeError as e:
#         raise HTTPException(status_code=500, detail=str(e))
#     except FileNotFoundError as e:
#         raise HTTPException(status_code=500, detail=f"Data file not found: {e}")

#     score_map: dict = {
#         str(row["post_id"]): {
#             "final_score":    float(row["final_score"]),
#             "content_score":  float(row["content_score"]),
#             "trending_score": float(row["trending_score"]),
#             "random_score":   float(row["random_score"]),
#         }
#         for _, row in df.iterrows()
#     }
#     all_scored_ids = list(score_map.keys())

#     # Step 3  Filter to DB-existing posts
#     try:
#         existing_ids = filter_posts_existing_in_db(all_scored_ids)
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"DB filter error: {e}")

#     print(
#         f"   {len(all_scored_ids)} scored | "
#         f"{len(existing_ids)} in DB | "
#         f"top {top_n} returned"
#     )

#     final_ids = existing_ids[:top_n]
#     if not final_ids:
#         return RecommendationResponse(user_id=user_id, total_posts=0, top_n=top_n, posts=[])

#     # Step 4+5  Fetch enriched details
#     try:
#         details_map = fetch_post_details(final_ids, requesting_user_id=user_id)
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"DB detail error: {e}")

#     # Step 6  Assemble in ranked order
#     posts: List[PostDetail] = []
#     for pid in final_ids:
#         detail = details_map.get(pid)
#         if not detail:
#             continue
#         scores = score_map[pid]
#         posts.append(PostDetail(
#             **detail,
#             final_score    = scores["final_score"],
#             content_score  = scores["content_score"],
#             trending_score = scores["trending_score"],
#             random_score   = scores["random_score"],
#         ))

#     return RecommendationResponse(
#         user_id     = user_id,
#         total_posts = len(posts),
#         top_n       = top_n,
#         posts       = posts,
#     )


# # SCHEDULER SCRIPTS
# SCRIPTS = {
#     "embeddings": [
#         "embedding/post_embeddings.py",
#         "embedding/user_embedding.py",
#     ],
#     "scores": [
#         "score/trending_score.py",
#     ],
# }


# def run_script(script_path: str):
#     """Run a single script and log result."""
#     abs_path    = os.path.abspath(script_path)
#     script_name = os.path.basename(script_path)
#     try:
#         result = subprocess.run(
#             ["python", abs_path],
#             capture_output=True,
#             text=True,
#             cwd=os.path.dirname(abs_path),
#         )
#         if result.returncode == 0:
#             print(f"   [{script_name}] completed successfully.")
#         else:
#             print(f"   [{script_name}] failed:\n{result.stderr.strip()}")
#     except Exception as e:
#         print(f"   [{script_name}] exception: {e}")


# def run_pipeline():
#     """
#     Step 1: Run embedding scripts in parallel.
#     Step 2: Run trending_score.py (after embeddings finish).
#     """
#     print("\n [Pipeline] Starting...")

#     with ThreadPoolExecutor(max_workers=2) as executor:
#         futures = [executor.submit(run_script, s) for s in SCRIPTS["embeddings"]]
#         for f in futures:
#             f.result()

#     with ThreadPoolExecutor(max_workers=2) as executor:
#         futures = [executor.submit(run_script, s) for s in SCRIPTS["scores"]]
#         for f in futures:
#             f.result()

#     print(" [Pipeline] Complete.\n")





# scheduler = BackgroundScheduler()
# scheduler.add_job(run_pipeline,     "interval", minutes=5,  id="pipeline_job")
# scheduler.start()

# print(" Scheduler started:")
# print("    run_pipeline()             every 5 minutes")
# print("      embeddings (parallel)")
# print("      trending_score.py")


# if __name__ == "__main__":
#     uid = sys.argv[1].strip() if len(sys.argv) >= 2 else input("Enter User ID: ").strip()

#     if not uid:
#         print(" No user ID provided.")
#         sys.exit(1)

#     # Validate user
#     try:
#         info = validate_user_in_db(uid)
#         print(f"   DB user: {info['username']} ({uid})")
#     except ValueError as e:
#         print(f"\n {e}")
#         sys.exit(1)
#     except Exception as e:
#         print(f"\n DB error: {e}")
#         sys.exit(1)

#     # Get recommendations
#     try:
#         df           = get_recommendations(uid, top_n=TOP_N, save_csv=False)
#         all_ids      = [str(pid) for pid in df["post_id"].tolist()]
#         existing_ids = filter_posts_existing_in_db(all_ids)
#         final_ids    = existing_ids[:TOP_N]
#         score_map    = {str(row["post_id"]): row for _, row in df.iterrows()}

#         print(f"   {len(all_ids)} scored | {len(existing_ids)} in DB | top {len(final_ids)}")
       
#         print(f"  Top {len(final_ids)} Posts  |  User: {uid}")
        
#         print(f"  {'#':<4} {'Post ID':<38} {'Final':>7} {'Content':>8} {'Trend':>7} {'Rand':>6}")
        

#         for rank, pid in enumerate(final_ids, 1):
#             r = score_map[pid]
#             print(
#                 f"  {rank:<4} {pid:<38} "
#                 f"{r['final_score']:>7.4f} {r['content_score']:>8.4f} "
#                 f"{r['trending_score']:>7.4f} {r['random_score']:>6.4f}"
#             )

#         print(f"{''*76}\n")

#     except (ValueError, RuntimeError) as e:
#         print(f"\n {e}")
#         sys.exit(1)
#     except FileNotFoundError as e:
#         print(f"\n File not found: {e}")
#         sys.exit(1)
