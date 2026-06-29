from __future__ import annotations

import argparse
import base64
import binascii
from contextlib import contextmanager
import csv
import datetime as dt
import hashlib
import hmac
import io
import json
import os
import secrets
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("DB_PATH", ROOT / "health_check.sqlite3")).resolve()
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "").strip()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
ADMIN_SESSION_SECRET = (
    os.environ.get("ADMIN_SESSION_SECRET", "").encode("utf-8")
    or secrets.token_bytes(32)
)
ADMIN_SESSION_HOURS = int(os.environ.get("ADMIN_SESSION_HOURS", "8"))
ADMIN_COOKIE_SECURE = os.environ.get("ADMIN_COOKIE_SECURE", "0") == "1"
SESSION_COOKIE_NAME = "health_check_admin"
LOGIN_WINDOW_SECONDS = 300
LOGIN_MAX_ATTEMPTS = 5
LOGIN_ATTEMPTS: dict[str, list[float]] = {}
LOGIN_ATTEMPTS_LOCK = threading.Lock()


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def db_connection() -> sqlite3.Connection:
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with db_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS survey_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                survey_date TEXT NOT NULL,
                total_score INTEGER NOT NULL,
                smoking TEXT DEFAULT '',
                steps TEXT DEFAULT '',
                ldl TEXT DEFAULT '',
                bp TEXT DEFAULT '',
                bmi TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_survey_results_name_date
            ON survey_results(name, survey_date)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_survey_results_survey_date
            ON survey_results(survey_date)
            """
        )


def parse_date(value: object) -> str:
    if value is None:
        raise ValueError("date is required")

    text = str(value).strip()
    if not text:
        raise ValueError("date is required")

    # Accept full timestamps from form/spreadsheet exports and store only the date.
    text = text.replace(".", "-").replace("/", "-")
    date_part = text.split("T", 1)[0].split(" ", 1)[0]
    try:
        return dt.date.fromisoformat(date_part).isoformat()
    except ValueError as exc:
        raise ValueError("date must be YYYY-MM-DD") from exc


def parse_score(value: object) -> int | float:
    try:
        score = float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("totalScore must be a number") from exc

    if not 0 <= score <= 100:
        raise ValueError("totalScore must be between 0 and 100")
    return int(score) if score.is_integer() else score


def normalize_result(payload: dict[str, object]) -> dict[str, object]:
    name = str(payload.get("name", "")).strip()
    if not name:
        raise ValueError("name is required")

    date_value = payload.get("date", payload.get("surveyDate", payload.get("survey_date")))
    score_value = payload.get("totalScore", payload.get("total_score"))

    return {
        "name": name,
        "survey_date": parse_date(date_value),
        "total_score": parse_score(score_value),
        "smoking": str(payload.get("smoking", "")).strip(),
        "steps": str(payload.get("steps", "")).strip(),
        "ldl": str(payload.get("ldl", payload.get("LDL", ""))).strip(),
        "bp": str(payload.get("bp", "")).strip(),
        "bmi": str(payload.get("bmi", payload.get("BMI", ""))).strip(),
    }


def insert_result(payload: dict[str, object]) -> int:
    row = normalize_result(payload)
    with db_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO survey_results
                (name, survey_date, total_score, smoking, steps, ldl, bp, bmi)
            VALUES
                (:name, :survey_date, :total_score, :smoking, :steps, :ldl, :bp, :bmi)
            """,
            row,
        )
        return int(cursor.lastrowid)


def result_to_api(row: sqlite3.Row) -> dict[str, object]:
    return {
        "date": row["survey_date"],
        "totalScore": row["total_score"],
        "smoking": row["smoking"],
        "steps": row["steps"],
        "ldl": row["ldl"],
        "bp": row["bp"],
        "bmi": row["bmi"],
    }


def get_name_results(name: str) -> list[dict[str, object]]:
    with db_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                s.survey_date,
                s.total_score,
                s.smoking,
                s.steps,
                s.ldl,
                s.bp,
                s.bmi
            FROM survey_results s
            WHERE s.name = ?
              AND s.id = (
                SELECT s2.id
                FROM survey_results s2
                WHERE s2.name = s.name
                  AND s2.survey_date = s.survey_date
                ORDER BY s2.total_score DESC, s2.id DESC
                LIMIT 1
              )
            ORDER BY s.survey_date
            """,
            (name,),
        ).fetchall()

    return [result_to_api(row) for row in rows]


def get_score_history(name: str) -> list[dict[str, object]]:
    return [
        {"date": row["date"], "totalScore": row["totalScore"]}
        for row in get_name_results(name)[-4:]
    ]


def get_all_results() -> list[dict[str, object]]:
    with db_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                id,
                name,
                survey_date,
                total_score,
                smoking,
                steps,
                ldl,
                bp,
                bmi,
                created_at
            FROM survey_results
            ORDER BY survey_date DESC, id DESC
            """
        ).fetchall()

    return [
        {
            "id": row["id"],
            "name": row["name"],
            "date": row["survey_date"],
            "totalScore": row["total_score"],
            "smoking": row["smoking"],
            "steps": row["steps"],
            "ldl": row["ldl"],
            "bp": row["bp"],
            "bmi": row["bmi"],
            "createdAt": row["created_at"],
        }
        for row in rows
    ]


def get_database_summary() -> dict[str, object]:
    with db_connection() as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total_count,
                COUNT(DISTINCT name) AS participant_count,
                ROUND(AVG(total_score), 1) AS average_score,
                MAX(survey_date) AS latest_date
            FROM survey_results
            """
        ).fetchone()

    return {
        "totalCount": row["total_count"],
        "participantCount": row["participant_count"],
        "averageScore": row["average_score"],
        "latestDate": row["latest_date"],
    }


def build_results_csv() -> bytes:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        ["ID", "이름", "날짜", "총점", "흡연", "걸음수", "LDL", "혈압", "BMI", "등록시각"]
    )

    for row in get_all_results():
        writer.writerow(
            [
                row["id"],
                row["name"],
                row["date"],
                row["totalScore"],
                row["smoking"],
                row["steps"],
                row["ldl"],
                row["bp"],
                row["bmi"],
                row["createdAt"],
            ]
        )

    return output.getvalue().encode("utf-8-sig")


def admin_credentials_configured() -> bool:
    return bool(ADMIN_USERNAME and ADMIN_PASSWORD)


def urlsafe_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def urlsafe_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def create_session_token(now: int | None = None) -> str:
    issued_at = int(time.time() if now is None else now)
    payload = {
        "username": ADMIN_USERNAME,
        "expiresAt": issued_at + ADMIN_SESSION_HOURS * 3600,
        "nonce": secrets.token_urlsafe(16),
    }
    encoded_payload = urlsafe_encode(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    )
    signature = hmac.new(
        ADMIN_SESSION_SECRET,
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{encoded_payload}.{urlsafe_encode(signature)}"


def verify_session_token(token: str, now: int | None = None) -> bool:
    try:
        encoded_payload, encoded_signature = token.split(".", 1)
        expected_signature = hmac.new(
            ADMIN_SESSION_SECRET,
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(
            urlsafe_decode(encoded_signature), expected_signature
        ):
            return False

        payload = json.loads(urlsafe_decode(encoded_payload).decode("utf-8"))
        current_time = int(time.time() if now is None else now)
        return (
            payload.get("username") == ADMIN_USERNAME
            and int(payload.get("expiresAt", 0)) > current_time
        )
    except (ValueError, TypeError, json.JSONDecodeError, binascii.Error):
        return False


def credentials_match(username: object, password: object) -> bool:
    if not admin_credentials_configured():
        return False
    return hmac.compare_digest(str(username), ADMIN_USERNAME) and hmac.compare_digest(
        str(password), ADMIN_PASSWORD
    )


def login_is_rate_limited(client_ip: str, now: float | None = None) -> bool:
    current_time = time.monotonic() if now is None else now
    cutoff = current_time - LOGIN_WINDOW_SECONDS
    with LOGIN_ATTEMPTS_LOCK:
        attempts = [
            attempted_at
            for attempted_at in LOGIN_ATTEMPTS.get(client_ip, [])
            if attempted_at >= cutoff
        ]
        LOGIN_ATTEMPTS[client_ip] = attempts
        return len(attempts) >= LOGIN_MAX_ATTEMPTS


def record_failed_login(client_ip: str, now: float | None = None) -> None:
    attempted_at = time.monotonic() if now is None else now
    with LOGIN_ATTEMPTS_LOCK:
        LOGIN_ATTEMPTS.setdefault(client_ip, []).append(attempted_at)


def clear_failed_logins(client_ip: str) -> None:
    with LOGIN_ATTEMPTS_LOCK:
        LOGIN_ATTEMPTS.pop(client_ip, None)


class HealthCheckHandler(BaseHTTPRequestHandler):
    server_version = "HealthCheckServer/1.0"

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)

        try:
            if path in {"/", "/index.html"}:
                self.send_file(ROOT / "index.html", "text/html; charset=utf-8")
            elif path == "/admin/login.html":
                if self.is_admin_authenticated():
                    self.redirect("/admin.html")
                else:
                    self.send_file(
                        ROOT / "login.html",
                        "text/html; charset=utf-8",
                        cache_control="no-store",
                    )
            elif path == "/admin.html":
                if not self.require_admin_page():
                    return
                self.send_file(
                    ROOT / "admin.html",
                    "text/html; charset=utf-8",
                    cache_control="no-store",
                )
            elif path == "/api/health":
                self.handle_health()
            elif path == "/api/admin/session":
                self.send_json(
                    {
                        "authenticated": self.is_admin_authenticated(),
                        "configured": admin_credentials_configured(),
                    },
                    headers={"Cache-Control": "no-store"},
                )
            elif path == "/api/name-summary":
                if not self.require_admin_api():
                    return
                self.handle_name_summary()
            elif path == "/api/search-name":
                if not self.require_admin_api():
                    return
                self.handle_search_name(query)
            elif path == "/api/recent-3days":
                if not self.require_admin_api():
                    return
                self.handle_recent_3days()
            elif path == "/api/results-summary":
                if not self.require_admin_api():
                    return
                self.send_json({"summary": get_database_summary()})
            elif path == "/api/results":
                if not self.require_admin_api():
                    return
                self.send_json(
                    {
                        "data": get_all_results(),
                        "summary": get_database_summary(),
                    }
                )
            elif path == "/api/export.csv":
                if not self.require_admin_api():
                    return
                self.send_bytes(
                    build_results_csv(),
                    "text/csv; charset=utf-8",
                    'attachment; filename="health-check-results.csv"',
                    headers={"Cache-Control": "no-store"},
                )
            else:
                self.send_json({"error": "Not found"}, status=404)
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=500)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        try:
            if path == "/api/admin/login":
                self.handle_admin_login()
            elif path == "/api/admin/logout":
                self.handle_admin_logout()
            elif path == "/api/survey-results":
                payload = self.read_json()
                result_id = insert_result(payload)
                name = str(payload.get("name", "")).strip()
                self.send_json(
                    {
                        "ok": True,
                        "id": result_id,
                        "data": get_score_history(name),
                    },
                    status=201,
                )
            else:
                self.send_json({"error": "Not found"}, status=404)
        except ValueError as exc:
            self.send_json({"error": str(exc)}, status=400)
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=500)

    def read_json(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        data = json.loads(body or "{}")
        if not isinstance(data, dict):
            raise ValueError("JSON object is required")
        return data

    def send_json(
        self,
        payload: dict[str, object],
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def send_file(
        self,
        path: Path,
        content_type: str,
        cache_control: str | None = None,
    ) -> None:
        if not path.exists():
            self.send_json({"error": "File not found"}, status=404)
            return

        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if cache_control:
            self.send_header("Cache-Control", cache_control)
        self.end_headers()
        self.wfile.write(body)

    def send_bytes(
        self,
        body: bytes,
        content_type: str,
        content_disposition: str | None = None,
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if content_disposition:
            self.send_header("Content-Disposition", content_disposition)
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, location: str) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def get_cookie(self, name: str) -> str:
        cookie_header = self.headers.get("Cookie", "")
        for item in cookie_header.split(";"):
            key, separator, value = item.strip().partition("=")
            if separator and key == name:
                return value
        return ""

    def is_admin_authenticated(self) -> bool:
        return admin_credentials_configured() and verify_session_token(
            self.get_cookie(SESSION_COOKIE_NAME)
        )

    def require_admin_page(self) -> bool:
        if self.is_admin_authenticated():
            return True
        self.redirect("/admin/login.html")
        return False

    def require_admin_api(self) -> bool:
        if self.is_admin_authenticated():
            return True
        self.send_json(
            {"error": "Authentication required"},
            status=401,
            headers={"Cache-Control": "no-store"},
        )
        return False

    def session_cookie(self, token: str, max_age: int) -> str:
        parts = [
            f"{SESSION_COOKIE_NAME}={token}",
            "Path=/",
            "HttpOnly",
            "SameSite=Strict",
            f"Max-Age={max_age}",
        ]
        if ADMIN_COOKIE_SECURE or self.headers.get("X-Forwarded-Proto") == "https":
            parts.append("Secure")
        return "; ".join(parts)

    def handle_admin_login(self) -> None:
        if not admin_credentials_configured():
            self.send_json(
                {"error": "Admin credentials are not configured"},
                status=503,
                headers={"Cache-Control": "no-store"},
            )
            return

        client_ip = self.client_address[0]
        if login_is_rate_limited(client_ip):
            self.send_json(
                {"error": "Too many login attempts. Try again later."},
                status=429,
                headers={"Cache-Control": "no-store"},
            )
            return

        payload = self.read_json()
        if not credentials_match(payload.get("username"), payload.get("password")):
            record_failed_login(client_ip)
            self.send_json(
                {"error": "Invalid username or password"},
                status=401,
                headers={"Cache-Control": "no-store"},
            )
            return

        clear_failed_logins(client_ip)
        max_age = ADMIN_SESSION_HOURS * 3600
        self.send_json(
            {"ok": True},
            headers={
                "Set-Cookie": self.session_cookie(create_session_token(), max_age),
                "Cache-Control": "no-store",
            },
        )

    def handle_admin_logout(self) -> None:
        self.send_json(
            {"ok": True},
            headers={
                "Set-Cookie": self.session_cookie("", 0),
                "Cache-Control": "no-store",
            },
        )

    def handle_health(self) -> None:
        with db_connection() as conn:
            total = conn.execute("SELECT COUNT(*) AS count FROM survey_results").fetchone()

        self.send_json(
            {
                "ok": True,
                "surveyResultCount": total["count"]
                if self.is_admin_authenticated()
                else None,
            }
        )

    def handle_name_summary(self) -> None:
        with db_connection() as conn:
            rows = conn.execute(
                """
                SELECT name, COUNT(DISTINCT survey_date) AS count
                FROM survey_results
                GROUP BY name
                ORDER BY name
                """
            ).fetchall()

        self.send_json({"data": [dict(row) for row in rows]})

    def handle_search_name(self, query: dict[str, list[str]]) -> None:
        name = (query.get("name") or [""])[0].strip()
        if not name:
            self.send_json({"error": "name is required"}, status=400)
            return

        self.send_json({"data": get_name_results(name)})

    def handle_recent_3days(self) -> None:
        with db_connection() as conn:
            latest = conn.execute(
                "SELECT MAX(survey_date) AS survey_date FROM survey_results"
            ).fetchone()["survey_date"]

            if latest is None:
                self.send_json({"data": []})
                return

            latest_date = dt.date.fromisoformat(latest)
            cutoff = (latest_date - dt.timedelta(days=2)).isoformat()
            rows = conn.execute(
                """
                SELECT DISTINCT name
                FROM survey_results
                WHERE survey_date BETWEEN ? AND ?
                ORDER BY name
                """,
                (cutoff, latest),
            ).fetchall()

        self.send_json(
            {
                "data": [row["name"] for row in rows],
                "from": cutoff,
                "to": latest,
            }
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Health check admin API server")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", default=int(os.environ.get("PORT", "8000")), type=int)
    args = parser.parse_args()

    init_db()
    if not admin_credentials_configured():
        print(
            "WARNING: ADMIN_USERNAME and ADMIN_PASSWORD are not configured; "
            "admin login will be unavailable."
        )

    server = ThreadingHTTPServer((args.host, args.port), HealthCheckHandler)
    print(f"Serving health survey at http://{args.host}:{args.port}/")
    print(f"Serving admin dashboard at http://{args.host}:{args.port}/admin.html")
    print(f"SQLite database: {DB_PATH}")
    server.serve_forever()


if __name__ == "__main__":
    main()
