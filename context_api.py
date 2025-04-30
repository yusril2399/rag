from fastapi import FastAPI
from pydantic import BaseModel
from context_sources import fetch_context_sources_scored

app = FastAPI()

class ContextRequest(BaseModel):
    title: str

@app.post("/get-context/")
def get_context(req: ContextRequest):
    context = fetch_context_sources_scored(req.title)
    return {"context": context}
