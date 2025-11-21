"""
Database Schemas for AI Co‑Founder OS

Each Pydantic model represents a collection in MongoDB. The collection name is the
lowercased class name. Example: class Task -> "task" collection.

These schemas define the core entities for an initial MVP:
- Company: high-level context and objectives
- User: team members who interact with the AI
- Task: work items with priority metadata
- Message: chat history between users and the AI co‑founder
"""

from typing import Optional, List, Literal
from pydantic import BaseModel, Field


class Company(BaseModel):
    name: str = Field(..., description="Company name")
    mission: Optional[str] = Field(None, description="Company mission statement")
    north_star_metric: Optional[str] = Field(
        None, description="Primary metric used to guide prioritization"
    )
    stage: Optional[Literal["idea", "mvp", "pmf", "scale"]] = Field(
        "mvp", description="Company stage"
    )


class User(BaseModel):
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address")
    role: Optional[str] = Field(None, description="Role or function, e.g. Growth, Ops")
    is_active: bool = Field(True, description="Whether user is active")


class Task(BaseModel):
    title: str = Field(..., description="Short task title")
    description: Optional[str] = Field(None, description="Task details and acceptance criteria")
    domain: Optional[
        Literal[
            "product",
            "growth",
            "sales",
            "ops",
            "finance",
            "people",
            "legal",
            "data",
            "research",
            "general",
        ]
    ] = Field("general", description="Business area for the task")
    impact: int = Field(5, ge=1, le=10, description="Estimated impact (1-10)")
    effort: int = Field(3, ge=1, le=10, description="Estimated effort (1-10)")
    urgency: int = Field(5, ge=1, le=10, description="How time-sensitive (1-10)")
    status: Literal["backlog", "in_progress", "done", "blocked"] = Field(
        "backlog", description="Workflow status"
    )
    assignee: Optional[str] = Field(None, description="Assigned user email (if any)")


class Message(BaseModel):
    sender: Literal["user", "ai"] = Field(..., description="Message author")
    text: str = Field(..., description="Message content")
    user_email: Optional[str] = Field(None, description="User who owns the conversation context")
    topic: Optional[str] = Field("general", description="Thread topic or channel")


# Note for the built-in database viewer:
# GET /schema endpoint in the backend exposes these models for reference.
