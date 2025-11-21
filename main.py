import os
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import Company, User, Task, Message

app = FastAPI(title="AI Co‑Founder OS API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------------
# Helpers
# ----------------------------

def to_str_id(value: Any):
    try:
        return str(value)
    except Exception:
        return value


def serialize_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    if not doc:
        return doc
    doc = {**doc}
    if "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    # Convert any nested ObjectIds to strings
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            doc[k] = str(v)
    return doc


def score_task(t: Dict[str, Any]) -> int:
    impact = int(t.get("impact", 5))
    effort = int(t.get("effort", 3))
    urgency = int(t.get("urgency", 5))
    return (impact * 2) + urgency - effort


# ----------------------------
# Health + Root
# ----------------------------

@app.get("/")
def read_root():
    return {"message": "AI Co‑Founder OS Backend running"}


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": [],
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, "name") else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:80]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"

    return response


# ----------------------------
# Schema Introspection
# ----------------------------

@app.get("/schema")
def get_schema():
    models = {
        "company": Company.model_json_schema(),
        "user": User.model_json_schema(),
        "task": Task.model_json_schema(),
        "message": Message.model_json_schema(),
    }
    return models


# ----------------------------
# Task Endpoints
# ----------------------------

class TaskCreate(Task):
    pass


@app.post("/api/tasks")
def create_task(payload: TaskCreate):
    task_dict = payload.model_dump()
    task_id = create_document("task", task_dict)
    return {"id": task_id}


@app.get("/api/tasks")
def list_tasks(status: Optional[str] = Query(None)):
    filter_q: Dict[str, Any] = {}
    if status:
        filter_q["status"] = status
    docs = get_documents("task", filter_q)
    enriched = []
    for d in docs:
        d = serialize_doc(d)
        d["score"] = score_task(d)
        enriched.append(d)
    enriched.sort(key=lambda x: x.get("score", 0), reverse=True)
    return {"items": enriched}


@app.get("/api/tasks/next")
def next_task(user_email: Optional[str] = Query(None)):
    # Prefer backlog tasks
    backlog = get_documents("task", {"status": "backlog"})
    if not backlog:
        # If empty, consider blocked to surface awareness but don't auto-assign
        blocked = get_documents("task", {"status": "blocked"})
        pool = blocked
    else:
        pool = backlog

    if not pool:
        return {"task": None, "message": "No tasks available. Create one to get started."}

    # Prefer tasks already assigned to the user, otherwise unassigned
    def pref_score(t):
        s = score_task(t)
        if user_email and t.get("assignee") == user_email:
            s += 5
        if not t.get("assignee"):
            s += 2
        return s

    best = sorted(pool, key=pref_score, reverse=True)[0]
    best_ser = serialize_doc(best)

    # Auto-assign and move to in_progress if user provided and task is backlog
    if user_email and best.get("status") == "backlog":
        db["task"].update_one(
            {"_id": best["_id"]},
            {"$set": {"status": "in_progress", "assignee": user_email}},
        )
        best_ser["status"] = "in_progress"
        best_ser["assignee"] = user_email

    best_ser["score"] = score_task(best)
    return {"task": best_ser}


class TaskStatusUpdate(BaseModel):
    status: str


@app.post("/api/tasks/{task_id}/status")
def update_task_status(task_id: str, payload: TaskStatusUpdate):
    try:
        oid = ObjectId(task_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid task id")

    res = db["task"].update_one({"_id": oid}, {"$set": {"status": payload.status}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"ok": True}


# ----------------------------
# Messaging & Assistant
# ----------------------------

class MessageCreate(BaseModel):
    sender: str
    text: str
    user_email: Optional[str] = None
    topic: Optional[str] = "general"


@app.post("/api/messages")
def create_message(payload: MessageCreate):
    # Store user message
    msg_dict = payload.model_dump()
    create_document("message", msg_dict)

    # Generate a lightweight assistant reply based on current tasks
    tasks = get_documents("task")
    tasks_sorted = sorted(tasks, key=score_task, reverse=True)
    top = [serialize_doc(t) for t in tasks_sorted[:3]]
    if top:
        bullets = "\n".join(
            [
                f"- {t.get('title')} (score {score_task(t)}) — domain: {t.get('domain', 'general')}"
                for t in top
            ]
        )
        reply = (
            "Basierend auf deinem aktuellen Backlog würde ich diese Schritte priorisieren:\n"
            f"{bullets}\n\n"
            "Nutze den Button 'Ich bin frei', um dir direkt den nächsten Schritt zuzuweisen."
        )
    else:
        reply = (
            "Ich sehe noch keine Aufgaben. Erstelle 3-5 klare, wirkungsstarke Tasks mit Impact,"
            " Effort und Urgency – dann priorisiere ich sie automatisch."
        )

    ai_msg = {
        "sender": "ai",
        "text": reply,
        "user_email": payload.user_email,
        "topic": payload.topic or "general",
    }
    create_document("message", ai_msg)

    return {"ok": True}


@app.get("/api/messages")
def list_messages(user_email: Optional[str] = Query(None), topic: Optional[str] = Query(None)):
    q: Dict[str, Any] = {}
    if user_email:
        q["user_email"] = user_email
    if topic:
        q["topic"] = topic
    msgs = get_documents("message", q)
    msgs = [serialize_doc(m) for m in msgs]
    # Basic ordering by created_at if present
    msgs.sort(key=lambda m: m.get("created_at", 0))
    return {"items": msgs}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
