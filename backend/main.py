from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db.database import Base, engine
from app.api import complaints

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Complaint Management System API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(complaints.router)

@app.get("/health")
def health_check():
    return {"status": "ok"}