
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Str
from typing import Optional

from tools.auth import register_student, login_student
from tools.student_tools import get_student_profile, create_support_request
from memory.store import save_memory, get_memories, delete_memory
from retrieval.policy import retrieve_policy, list_available_documents

app = FastAPI(
    title="UniPilot API",
    description="Agentic AI Student Support Assistant Backend",
    version="1.0.0"
)


# -------------------------
# Request Models
# -------------------------

class RegisterRequest(BaseModel):
    name: str
    email: Str
    programme: str
    password: str


class LoginRequest(BaseModel):
    email: Str
    password: str


class QuestionRequest(BaseModel):
    student_id: str
    question: str


class MemoryRequest(BaseModel):
    student_id: str
    key: str
    value: str


class SupportRequest(BaseModel):
    student_id: str
    subject: str
    description: str


# -------------------------
# Home / Health Check
# -------------------------

@app.get("/")
def home():
    return {
        "success": True,
        "message": "Welcome to UniPilot API",
        "status": "Running"
    }


@app.get("/health")
def health_check():
    return {"status": "healthy"}


# -------------------------
# Authentication
# -------------------------

@app.post("/auth/register")
def register(request: RegisterRequest):
    result = register_student(
        request.name,
        request.email,
        request.programme,
        request.password
    )
    return result


@app.post("/auth/login")
def login(request: LoginRequest):
    result = login_student(request.email, request.password)
    return result


# -------------------------
# Student Profile
# -------------------------

@app.get("/students/{student_id}")
def student_profile(student_id: str):
    result = get_student_profile(student_id)

    if not result:
        raise HTTPException(status_code=404, detail="Student not found")

    return result


# -------------------------
# Academic PDF Retrieval
# -------------------------

@app.post("/academic/ask")
def ask_academic_question(request: QuestionRequest):
    result = retrieve_policy(request.question, top_k=4)

    return {
        "success": result.get("success", False),
        "question": request.question,
        "answer_type": "PDF-based retrieval",
        "evidence": result.get("chunks", []),
        "message": result.get("message", "")
    }


@app.get("/academic/documents")
def academic_documents():
    return {
        "documents": list_available_documents()
    }


# -------------------------
# Student Memory
# -------------------------

@app.get("/memory/{student_id}")
def student_memories(student_id: str):
    return {
        "success": True,
        "memories": get_memories(student_id)
    }


@app.post("/memory/save")
def save_student_memory(request: MemoryRequest):
    return save_memory(
        request.student_id,
        request.key,
        request.value
    )


@app.delete("/memory/{student_id}/{key}")
def remove_student_memory(student_id: str, key: str):
    return delete_memory(student_id, key)


# -------------------------
# Support Requests
# -------------------------

@app.post("/support/request")
def submit_support_request(request: SupportRequest):
    return create_support_request(
        request.student_id,
        request.subject,
        request.description
    )
