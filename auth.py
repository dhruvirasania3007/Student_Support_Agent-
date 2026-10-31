
import hashlib
import hmac
import secrets
import re
import uuid

from database.db import get_connection


# Secure password hashing using PBKDF2
HASH_ALGORITHM = "sha256"
ITERATIONS = 600_000


def hash_password(password):
    salt = secrets.token_hex(16)

    password_hash = hashlib.pbkdf2_hmac(
        HASH_ALGORITHM,
        password.encode("utf-8"),
        salt.encode("utf-8"),
        ITERATIONS
    ).hex()

    return f"{salt}${password_hash}"


def verify_password(password, stored_hash):
    try:
        salt, original_hash = stored_hash.split("$")

        new_hash = hashlib.pbkdf2_hmac(
            HASH_ALGORITHM,
            password.encode("utf-8"),
            salt.encode("utf-8"),
            ITERATIONS
        ).hex()

        return hmac.compare_digest(new_hash, original_hash)

    except (ValueError, AttributeError):
        return False


def register_student(name, email, programme, password):
    name = name.strip()
    email = email.strip().lower()
    programme = programme.strip()

    if not all([name, email, programme, password]):
        return {
            "success": False,
            "message": "All fields are required."
        }

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return {
            "success": False,
            "message": "Please enter a valid email address."
        }

    if len(password) < 8:
        return {
            "success": False,
            "message": "Password must contain at least 8 characters."
        }

    student_id = "STU" + uuid.uuid4().hex[:8].upper()
    password_hash = hash_password(password)

    try:
        with get_connection() as conn:
            conn.execute("""
                INSERT INTO students
                (student_id, name, programme, email, password_hash)
                VALUES (?, ?, ?, ?, ?)
            """, (
                student_id,
                name,
                programme,
                email,
                password_hash
            ))

        return {
            "success": True,
            "message": "Registration successful!",
            "student_id": student_id
        }

    except Exception as error:
        import sqlite3

        if isinstance(error, sqlite3.IntegrityError):
            return {
                "success": False,
                "message": "This email is already registered."
            }

        return {
            "success": False,
            "message": "Registration could not be completed."
        }


def login_student(email, password):
    email = email.strip().lower()

    if not email or not password:
        return {
            "success": False,
            "message": "Email and password are required."
        }

    with get_connection() as conn:
        student = conn.execute("""
            SELECT student_id, name, email, programme, password_hash
            FROM students
            WHERE email = ?
        """, (email,)).fetchone()

    if not student or not verify_password(
        password, student["password_hash"]
    ):
        return {
            "success": False,
            "message": "Invalid email or password."
        }

    return {
        "success": True,
        "message": "Login successful!",
        "student": {
            "student_id": student["student_id"],
            "name": student["name"],
            "email": student["email"],
            "programme": student["programme"]
        }
    }
