from fastapi import FastAPI
from suggestions import compute_user_suggestions

app = FastAPI()

@app.get("/")
def home():
    return {"message": "API running"}

@app.get("/suggestions/{user_id}")
def suggestions(user_id: str):
    return compute_user_suggestions(user_id)