# context_proxy_api.py
from fastapi import FastAPI
from pydantic import BaseModel
from context_sources import fetch_context_sources_scored  # ini yang kamu udah punya

app = FastAPI()

class ContextRequest(BaseModel):
    title: str


    
@app.post("/fetch-context/")
async def fetch_context(req: ContextRequest):
    context = fetch_context_sources_scored(
        topic=req.title,
        max_tokens=512,
        top_k_contexts=1,
        similarity_threshold=0.6
    )
    return {"context": context}




# from fastapi import FastAPI
# from pydantic import BaseModel
# import requests
# import logging

# app = FastAPI()

# class ContextRequest(BaseModel):
#     title: str

# # ==== Fungsi ambil context dari Railway ====
# def fetch_context_via_proxy(topic: str):
#     try:
#         response = requests.post(
#             "https://your-railway-service-url/fetch-context/",
#             json={"title": topic},
#             timeout=10
#         )
#         if response.status_code == 200:
#             return response.json().get("context", "")
#         return ""
#     except Exception as e:
#         logging.warning(f"[PROXY] Failed fetching context from proxy: {e}")
#         return ""

# # ==== Endpoint di Vast.ai ====
# @app.post("/get-context/")
# def get_context(req: ContextRequest):
#     context = fetch_context_via_proxy(req.title)  # <<< PANGGIL DARI RAILWAY
#     return {"context": context}