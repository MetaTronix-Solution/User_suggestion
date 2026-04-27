from typing import Any, List, Optional

from pydantic import BaseModel


class MediaItem(BaseModel):
    id:         str
    file:       str
    media_type: str


class CommentItem(BaseModel):
    id:         str
    username:   str
    avatar:     Optional[str]
    post:       str
    parent:     Optional[str]
    content:    str
    created_at: str


class SharedPostDetails(BaseModel):
    id:         str
    username:   str
    full_name:  Optional[str]
    avatar:     Optional[str]
    content:    Optional[str]
    created_at: str
    media:      List[MediaItem]


class PostDetail(BaseModel):
    id:                    str
    user_id:               str
    username:              str
    avatar:                Optional[str]
    content:               Optional[str]
    media:                 List[MediaItem]
    categories_detail:     List[Any]
    shared_post:           Optional[str]
    shared_post_details:   Optional[SharedPostDetails]
    reactions_count:       int
    like_count:            int
    reaction_types:        List[str]
    current_user_reaction: Optional[str]
    is_followed:           bool
    comments_count:        int
    comments:              List[CommentItem]
    views_count:           int
    created_at:            str
    updated_at:            str
    final_score:           float
    content_score:         float
    trending_score:        float
    random_score:          float


class RecommendationResponse(BaseModel):
    user_id:     str
    total_posts: int
    top_n:       int
    posts:       List[PostDetail]
