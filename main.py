# backend/main.py
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import config
from data.loader import load_all
from routes.columns import router as columns_router
from routes.sessions import router as sessions_router
from routes.roles import router as roles_router

app = FastAPI(title="Role Mining POC")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    load_all()


PREFIX = "/api/v1"
app.include_router(columns_router, prefix=PREFIX)
app.include_router(sessions_router, prefix=PREFIX)
app.include_router(roles_router, prefix=PREFIX)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=config.PORT, reload=True)