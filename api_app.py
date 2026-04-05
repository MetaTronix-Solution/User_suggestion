"""
User Suggestion API
FastAPI application for computing user recommendations
"""

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import List
import json
import pandas as pd
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import networkx as nx
from utils.suggestions import compute_user_suggestions, load_user_attributes_from_csv
import psycopg2
import uvicorn

app = FastAPI(
    title="User Suggestion API",
    description="Hybrid recommendation engine for user suggestions",
    version="1.0.0"
)


@app.get("/")
def root():
    """Root endpoint with API information"""
    return {
        "message": "Welcome to the User Suggestion API",
        "version": "1.0.0",
        "description": "Hybrid recommendation engine for user suggestions",
        "docs": "/docs",
        "health": "/health"
    }


# Response models
class ScoreBreakdown(BaseModel):
    text_score: float
    graph_score: float
    interest_score: float
    collab_score: float
    visual_score: dict = None


class Suggestion(BaseModel):
    user_id: str
    username: str
    full_name: str
    score: float
    breakdown: ScoreBreakdown


class SuggestionsResponse(BaseModel):
    target_user_id: str
    count: int
    suggestions: list[Suggestion]


class HealthResponse(BaseModel):
    status: str
    message: str


class UserAttributes(BaseModel):
    user_id: str
    username: str
    full_name: str
    hobbies: str | None = None
    address: str | None = None
    bio: str | None = None
    education: str | None = None
    occupation: str | None = None
    followers: list[str] = []
    following: list[str] = []
    interests: list[str] = []


class StatsResponse(BaseModel):
    api_version: str
    endpoints: list[str]
    docs: str


# Database connection helper
def get_db_connection():
    """Create a database connection"""
    try:
        conn = psycopg2.connect(
            host="182.93.94.220",
            port=5436,
            dbname="social_db",
            user="innovator_user",
            password="Nep@tronix9335%"
        )
        return conn
    except psycopg2.Error as e:
        print(f"Database connection error: {e}")
        return None


@app.get("/health", response_model=HealthResponse)
def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        message="API is running"
    )


@app.get("/api/suggestions/{target_user_id}", response_model=SuggestionsResponse)
def get_suggestions(
    target_user_id: str,
    top_n: int = Query(5, ge=1, le=50, description="Number of suggestions to return")
):
    """
    Get top suggestions for a user
    
    - **target_user_id**: User ID to get suggestions for
    - **top_n**: Number of suggestions to return (1-50, default: 5)
    """
    try:
        if not target_user_id:
            raise HTTPException(status_code=400, detail="target_user_id is required")
        
        # Compute suggestions
        suggestions = compute_user_suggestions(target_user_id, top_n=top_n)
        
        if not suggestions:
            return SuggestionsResponse(
                target_user_id=target_user_id,
                count=0,
                suggestions=[]
            )
        
        return SuggestionsResponse(
            target_user_id=target_user_id,
            count=len(suggestions),
            suggestions=suggestions
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@app.get("/api/suggestions/{target_user_id}/detailed", response_model=SuggestionsResponse)
def get_suggestions_detailed(
    target_user_id: str,
    top_n: int = Query(5, ge=1, le=50, description="Number of suggestions to return")
):
    """
    Get detailed suggestions with breakdown of scoring components
    
    - **target_user_id**: User ID to get suggestions for
    - **top_n**: Number of suggestions to return (1-50, default: 5)
    """
    try:
        if not target_user_id:
            raise HTTPException(status_code=400, detail="target_user_id is required")
        
        suggestions = compute_user_suggestions(target_user_id, top_n=top_n)
        
        # Add visual scores for frontend rendering
        for suggestion in suggestions:
            suggestion['breakdown']['visual_score'] = {
                'text': f"{suggestion['breakdown']['text_score']:.1%}",
                'graph': f"{suggestion['breakdown']['graph_score']:.1%}",
                'interest': f"{suggestion['breakdown']['interest_score']:.1%}",
                'collab': f"{suggestion['breakdown']['collab_score']:.1%}"
            }
        
        return SuggestionsResponse(
            target_user_id=target_user_id,
            count=len(suggestions),
            suggestions=suggestions
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@app.get("/api/users", response_model=list[UserAttributes])
def get_users():
    """Return all user attributes from the CSV data source."""
    return load_user_attributes_from_csv()


@app.get("/api/users/{user_id}", response_model=UserAttributes)
def get_user(user_id: str):
    """Return a specific user record from the CSV data source."""
    users = load_user_attributes_from_csv()
    for user in users:
        if user['user_id'] == user_id:
            return user
    raise HTTPException(status_code=404, detail="User not found")


@app.get("/api/stats", response_model=StatsResponse)
def get_stats():
    """Get API statistics and available endpoints"""
    return StatsResponse(
        api_version="1.0.0",
        endpoints=[
            "/",
            "/health",
            "/api/users",
            "/api/users/{user_id}",
            "/api/suggestions/{user_id}",
            "/api/suggestions/{user_id}/detailed",
            "/api/stats"
        ],
        docs="/docs"
    )


if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=5000)
