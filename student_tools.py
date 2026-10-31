
from database.db import get_connection


def get_student_profile(student_id):
    """Retrieve the logged-in student's profile."""

    with get_connection() as conn:
        student = conn.execute(
            """
            SELECT student_id, name, email, programme, created_at
            FROM students
            WHERE student_id = ?
            """,
            (student_id,)
        ).fetchone()

    if not student:
        return {
            "success": False,
            "message": "Student profile not found."
        }

    return {
        "success": True,
        "profile": dict(student)
    }


def create_support_request(student_id, subject, description):
    """Create a support request for the authenticated student."""

    if not subject or not subject.strip():
        return {
            "success": False,
            "message": "Please provide a request subject."
        }

    if not description or not description.strip():
        return {
            "success": False,
            "message": "Please provide a request description."
        }

    with get_connection() as conn:

        student = conn.execute(
            "SELECT student_id FROM students WHERE student_id = ?",
            (student_id,)
        ).fetchone()

        if not student:
            return {
                "success": False,
                "message": "Student record not found."
            }

        cursor = conn.execute(
            """
            INSERT INTO support_requests
            (student_id, subject, description)
            VALUES (?, ?, ?)
            """,
            (student_id, subject.strip(), description.strip())
        )

        return {
            "success": True,
            "ticket_id": cursor.lastrowid,
            "status": "Open",
            "message": "Support request created successfully."
        }
