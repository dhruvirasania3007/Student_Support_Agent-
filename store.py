
from database.db import get_connection


SENSITIVE_WORDS = [
    "password", "otp", "one time password",
    "pin", "credit card", "debit card",
    "bank account", "aadhaar", "pan number",
    "passport number"
]


def is_sensitive(text):
    text = text.lower()
    return any(word in text for word in SENSITIVE_WORDS)


def save_memory(student_id, key, value):
    """Save useful, non-sensitive information for a student."""

    if not key or not value or not key.strip() or not value.strip():
        return {
            "success": False,
            "message": "Memory key and value cannot be empty."
        }

    if is_sensitive(key) or is_sensitive(value):
        return {
            "success": False,
            "message": "Sensitive information cannot be stored."
        }

    with get_connection() as conn:
        student = conn.execute(
            "SELECT student_id FROM students WHERE student_id = ?",
            (student_id,)
        ).fetchone()

        if not student:
            return {
                "success": False,
                "message": "Student not found."
            }

        conn.execute("""
            INSERT INTO memories (student_id, memory_key, memory_value)
            VALUES (?, ?, ?)
            ON CONFLICT(student_id, memory_key)
            DO UPDATE SET memory_value = excluded.memory_value
        """, (student_id, key.strip(), value.strip()))

    return {
        "success": True,
        "message": "Memory saved successfully."
    }


def get_memories(student_id):
    """Retrieve only the specified student's memories."""

    with get_connection() as conn:
        student = conn.execute(
            "SELECT student_id FROM students WHERE student_id = ?",
            (student_id,)
        ).fetchone()

        if not student:
            return {
                "success": False,
                "message": "Student not found."
            }

        records = conn.execute("""
            SELECT memory_key, memory_value
            FROM memories
            WHERE student_id = ?
        """, (student_id,)).fetchall()

    return {
        "success": True,
        "memories": {
            record["memory_key"]: record["memory_value"]
            for record in records
        }
    }


def delete_memory(student_id, key):
    """Delete a specific memory belonging to the student."""

    with get_connection() as conn:
        cursor = conn.execute("""
            DELETE FROM memories
            WHERE student_id = ? AND memory_key = ?
        """, (student_id, key))

    if cursor.rowcount == 0:
        return {
            "success": False,
            "message": "Memory not found."
        }

    return {
        "success": True,
        "message": "Memory deleted successfully."
    }
