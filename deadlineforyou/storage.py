from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from deadlineforyou.domain import SessionStatus


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform_user_id TEXT UNIQUE NOT NULL,
    nickname TEXT NOT NULL,
    timezone TEXT NOT NULL,
    tone_preference TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    source_language TEXT NOT NULL,
    target_language TEXT NOT NULL,
    total_units INTEGER NOT NULL,
    completed_units INTEGER NOT NULL,
    deadline_at TEXT NOT NULL,
    unit_label TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    project_id INTEGER,
    mode TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ends_at TEXT NOT NULL,
    ended_at TEXT,
    reported_result TEXT,
    completed_units_delta INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    project_id INTEGER,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS project_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    source_text TEXT NOT NULL,
    translated_text TEXT NOT NULL DEFAULT '',
    source_chars INTEGER NOT NULL DEFAULT 0,
    source_lines INTEGER NOT NULL DEFAULT 0,
    source_segments INTEGER NOT NULL DEFAULT 0,
    translated_chars INTEGER NOT NULL DEFAULT 0,
    translated_lines INTEGER NOT NULL DEFAULT 0,
    translated_segments INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    due_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS reminder_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    reminder_type TEXT NOT NULL,
    reminder_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(user_id, reminder_type, reminder_date),
    FOREIGN KEY(user_id) REFERENCES users(id)
);
"""


def _iso(value: datetime) -> str:
    """_iso

    Args:
        value: 정규화할 datetime 값.

    Returns:
        str: UTC 기준 ISO-8601 문자열.
    """
    return value.astimezone(UTC).isoformat()


def _dt(value: str | None) -> datetime | None:
    """_dt

    Args:
        value: ISO-8601 문자열 또는 None.

    Returns:
        datetime | None: 입력이 있으면 파싱된 datetime, 없으면 None.
    """
    return datetime.fromisoformat(value) if value else None


class Database:
    def __init__(self, path: Path) -> None:
        """__init__

        Args:
            path: SQLite 데이터베이스 파일 경로.

        Returns:
            None: 경로를 저장하고 스키마를 초기화한다.
        """
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """connect

        Args:
            없음.

        Returns:
            Iterator[sqlite3.Connection]: row 매핑이 활성화된 관리형 SQLite 연결.
        """
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def initialize(self) -> None:
        """initialize

        Args:
            없음.

        Returns:
            None: 데이터베이스 스키마 존재를 보장한다.
        """
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def _text_metrics(self, text: str) -> dict[str, int]:
        """_text_metrics

        Args:
            text: 분석할 원문 또는 번역문 문자열.

        Returns:
            dict[str, int]: 글자 수, 줄 수, 세그먼트 수 집계.
        """
        normalized = (text or "").replace("\r\n", "\n").strip()
        if not normalized:
            return {
                "chars": 0,
                "lines": 0,
                "segments": 0,
            }

        lines = [line for line in normalized.split("\n") if line.strip()]
        segments = [segment for segment in lines if segment.strip()]
        return {
            "chars": len(normalized),
            "lines": len(lines),
            "segments": len(segments),
        }

    def _recalculate_project_progress(self, conn: sqlite3.Connection, project_id: int) -> None:
        """_recalculate_project_progress

        Args:
            conn: 재사용할 SQLite 연결.
            project_id: 집계할 프로젝트 식별자.

        Returns:
            None: 파일 기반 총량과 완료량을 프로젝트에 반영한다.
        """
        aggregate = conn.execute(
            """
            SELECT
                COUNT(*) AS file_count,
                COALESCE(SUM(source_segments), 0) AS total_segments,
                COALESCE(SUM(translated_segments), 0) AS translated_segments
            FROM project_files
            WHERE project_id = ?
            """,
            (project_id,),
        ).fetchone()
        if not aggregate or aggregate["file_count"] == 0:
            return

        conn.execute(
            """
            UPDATE projects
            SET total_units = ?, completed_units = ?
            WHERE id = ?
            """,
            (
                int(aggregate["total_segments"]),
                min(int(aggregate["translated_segments"]), int(aggregate["total_segments"])),
                project_id,
            ),
        )

    def create_user(self, payload: dict[str, Any]) -> sqlite3.Row:
        """create_user

        Args:
            payload: 사용자 생성 페이로드.

        Returns:
            sqlite3.Row: 저장된 사용자 행.
        """
        now = _iso(datetime.now(UTC))
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO users (platform_user_id, nickname, timezone, tone_preference, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    payload["platform_user_id"],
                    payload["nickname"],
                    payload["timezone"],
                    payload["tone_preference"],
                    now,
                ),
            )
            return conn.execute("SELECT * FROM users WHERE platform_user_id = ?", (payload["platform_user_id"],)).fetchone()

    def get_user(self, user_id: int) -> sqlite3.Row | None:
        """get_user

        Args:
            user_id: 내부 사용자 식별자.

        Returns:
            sqlite3.Row | None: 사용자를 찾으면 행, 없으면 None.
        """
        with self.connect() as conn:
            return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    def get_user_by_platform_id(self, platform_user_id: str) -> sqlite3.Row | None:
        """get_user_by_platform_id

        Args:
            platform_user_id: 외부 플랫폼에서 전달된 사용자 식별자.

        Returns:
            sqlite3.Row | None: 사용자를 찾으면 행, 없으면 None.
        """
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM users WHERE platform_user_id = ?",
                (platform_user_id,),
            ).fetchone()

    def list_users(self) -> list[sqlite3.Row]:
        """list_users

        Args:
            없음.

        Returns:
            list[sqlite3.Row]: 전체 사용자 목록.
        """
        with self.connect() as conn:
            return conn.execute("SELECT * FROM users ORDER BY id ASC").fetchall()

    def create_project(self, payload: dict[str, Any]) -> sqlite3.Row:
        """create_project

        Args:
            payload: 프로젝트 생성 페이로드.

        Returns:
            sqlite3.Row: 저장된 프로젝트 행.
        """
        now = _iso(datetime.now(UTC))
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO projects (
                    user_id, title, source_language, target_language, total_units,
                    completed_units, deadline_at, unit_label, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
                """,
                (
                    payload["user_id"],
                    payload["title"],
                    payload["source_language"],
                    payload["target_language"],
                    payload["total_units"],
                    payload["completed_units"],
                    _iso(payload["deadline_at"]),
                    payload["unit_label"],
                    now,
                ),
            )
            return conn.execute("SELECT * FROM projects WHERE id = ?", (cursor.lastrowid,)).fetchone()

    def create_project_file(self, payload: dict[str, Any]) -> sqlite3.Row:
        """create_project_file

        Args:
            payload: 프로젝트 파일 생성 페이로드.

        Returns:
            sqlite3.Row: 저장된 파일 행.
        """
        source_metrics = self._text_metrics(payload["source_text"])
        translated_metrics = self._text_metrics(payload.get("translated_text", ""))
        now = _iso(datetime.now(UTC))
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO project_files (
                    project_id, name, source_text, translated_text,
                    source_chars, source_lines, source_segments,
                    translated_chars, translated_lines, translated_segments,
                    status, due_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["project_id"],
                    payload["name"],
                    payload["source_text"],
                    payload.get("translated_text", ""),
                    source_metrics["chars"],
                    source_metrics["lines"],
                    source_metrics["segments"],
                    translated_metrics["chars"],
                    translated_metrics["lines"],
                    translated_metrics["segments"],
                    payload.get("status", "pending"),
                    _iso(payload["due_at"]) if payload.get("due_at") else None,
                    now,
                    now,
                ),
            )
            self._recalculate_project_progress(conn, payload["project_id"])
            return conn.execute("SELECT * FROM project_files WHERE id = ?", (cursor.lastrowid,)).fetchone()

    def get_project_file(self, file_id: int) -> sqlite3.Row | None:
        """get_project_file

        Args:
            file_id: 프로젝트 파일 식별자.

        Returns:
            sqlite3.Row | None: 파일을 찾으면 행, 없으면 None.
        """
        with self.connect() as conn:
            return conn.execute("SELECT * FROM project_files WHERE id = ?", (file_id,)).fetchone()

    def list_project_files(self, project_id: int) -> list[sqlite3.Row]:
        """list_project_files

        Args:
            project_id: 프로젝트 식별자.

        Returns:
            list[sqlite3.Row]: 프로젝트에 연결된 파일 목록.
        """
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT * FROM project_files
                WHERE project_id = ?
                ORDER BY COALESCE(due_at, '9999-12-31T00:00:00+00:00') ASC, created_at ASC
                """,
                (project_id,),
            ).fetchall()

    def update_project_file(self, file_id: int, updates: dict[str, Any]) -> sqlite3.Row | None:
        """update_project_file

        Args:
            file_id: 프로젝트 파일 식별자.
            updates: 부분 갱신 페이로드.

        Returns:
            sqlite3.Row | None: 파일을 찾으면 갱신된 행, 없으면 None.
        """
        with self.connect() as conn:
            existing = conn.execute("SELECT * FROM project_files WHERE id = ?", (file_id,)).fetchone()
            if not existing:
                return None

            merged = dict(existing)
            merged.update(updates)
            source_metrics = self._text_metrics(merged["source_text"])
            translated_metrics = self._text_metrics(merged["translated_text"])
            status = merged.get("status") or existing["status"]
            if translated_metrics["segments"] >= source_metrics["segments"] and source_metrics["segments"] > 0:
                status = "completed"
            elif translated_metrics["segments"] > 0:
                status = "in_progress"
            elif status == "completed":
                status = "pending"

            conn.execute(
                """
                UPDATE project_files
                SET name = ?, source_text = ?, translated_text = ?,
                    source_chars = ?, source_lines = ?, source_segments = ?,
                    translated_chars = ?, translated_lines = ?, translated_segments = ?,
                    status = ?, due_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    merged["name"],
                    merged["source_text"],
                    merged["translated_text"],
                    source_metrics["chars"],
                    source_metrics["lines"],
                    source_metrics["segments"],
                    translated_metrics["chars"],
                    translated_metrics["lines"],
                    translated_metrics["segments"],
                    status,
                    _iso(merged["due_at"]) if isinstance(merged.get("due_at"), datetime) else merged.get("due_at"),
                    _iso(datetime.now(UTC)),
                    file_id,
                ),
            )
            self._recalculate_project_progress(conn, existing["project_id"])
            return conn.execute("SELECT * FROM project_files WHERE id = ?", (file_id,)).fetchone()

    def project_workload_summary(self, project_id: int) -> sqlite3.Row:
        """project_workload_summary

        Args:
            project_id: 프로젝트 식별자.

        Returns:
            sqlite3.Row: 파일 기반 작업량 집계 행.
        """
        now = _iso(datetime.now(UTC))
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT
                    COALESCE(SUM(source_chars), 0) AS total_chars,
                    COALESCE(SUM(source_lines), 0) AS total_lines,
                    COALESCE(SUM(source_segments), 0) AS total_segments,
                    COALESCE(SUM(translated_chars), 0) AS translated_chars,
                    COALESCE(SUM(translated_lines), 0) AS translated_lines,
                    COALESCE(SUM(translated_segments), 0) AS translated_segments,
                    COUNT(*) AS file_count,
                    COALESCE(SUM(CASE WHEN translated_segments < source_segments THEN 1 ELSE 0 END), 0) AS remaining_file_count,
                    COALESCE(SUM(
                        CASE
                            WHEN due_at IS NOT NULL AND due_at < ? AND translated_segments < source_segments THEN 1
                            ELSE 0
                        END
                    ), 0) AS delayed_file_count
                FROM project_files
                WHERE project_id = ?
                """,
                (now, project_id),
            ).fetchone()

    def get_project(self, project_id: int) -> sqlite3.Row | None:
        """get_project

        Args:
            project_id: 프로젝트 식별자.

        Returns:
            sqlite3.Row | None: 프로젝트를 찾으면 행, 없으면 None.
        """
        with self.connect() as conn:
            return conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()

    def list_projects_for_user(self, user_id: int) -> list[sqlite3.Row]:
        """list_projects_for_user

        Args:
            user_id: 내부 사용자 식별자.

        Returns:
            list[sqlite3.Row]: 가장 가까운 마감 순으로 정렬된 프로젝트 목록.
        """
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM projects WHERE user_id = ? ORDER BY deadline_at ASC",
                (user_id,),
            ).fetchall()

    def get_active_project_for_user(self, user_id: int) -> sqlite3.Row | None:
        """get_active_project_for_user

        Args:
            user_id: 내부 사용자 식별자.

        Returns:
            sqlite3.Row | None: 사용자에게 연결된 가장 가까운 활성 프로젝트. 없으면 None.
        """
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT * FROM projects
                WHERE user_id = ? AND status = 'active'
                ORDER BY deadline_at ASC
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()

    def update_project(self, project_id: int, updates: dict[str, Any]) -> sqlite3.Row | None:
        """update_project

        Args:
            project_id: 프로젝트 식별자.
            updates: 갱신할 프로젝트 필드 일부.

        Returns:
            sqlite3.Row | None: 프로젝트를 찾으면 갱신된 행, 없으면 None.
        """
        if not updates:
            return self.get_project(project_id)

        fields: list[str] = []
        values: list[Any] = []
        for key, value in updates.items():
            fields.append(f"{key} = ?")
            if isinstance(value, datetime):
                values.append(_iso(value))
            else:
                values.append(value)
        values.append(project_id)
        with self.connect() as conn:
            # 필드명은 검증된 Pydantic 페이로드에서만 오므로 문자열 삽입 범위가 제한된다.
            conn.execute(f"UPDATE projects SET {', '.join(fields)} WHERE id = ?", values)
            return conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()

    def delete_project(self, project_id: int) -> sqlite3.Row | None:
        """delete_project

        Args:
            project_id: 삭제할 프로젝트 식별자.

        Returns:
            sqlite3.Row | None: 삭제 전 프로젝트 행. 없으면 None.
        """
        with self.connect() as conn:
            project = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            if not project:
                return None

            conn.execute("DELETE FROM project_files WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM sessions WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM messages WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))

            if project["status"] == "active":
                next_project = conn.execute(
                    """
                    SELECT id FROM projects
                    WHERE user_id = ?
                    ORDER BY deadline_at ASC, created_at ASC
                    LIMIT 1
                    """,
                    (project["user_id"],),
                ).fetchone()
                if next_project:
                    conn.execute("UPDATE projects SET status = 'active' WHERE id = ?", (next_project["id"],))

            return project

    def create_session(self, user_id: int, project_id: int | None, mode: str, duration_minutes: int) -> sqlite3.Row:
        """create_session

        Args:
            user_id: 내부 사용자 식별자.
            project_id: 연결된 프로젝트 식별자. 없을 수 있다.
            mode: 세션에 저장할 문자열 모드.
            duration_minutes: 예정된 세션 길이(분).

        Returns:
            sqlite3.Row: 저장된 세션 행.
        """
        started_at = datetime.now(UTC)
        ends_at = started_at + timedelta(minutes=duration_minutes)
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO sessions (
                    user_id, project_id, mode, duration_minutes, status,
                    started_at, ends_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    project_id,
                    mode,
                    duration_minutes,
                    SessionStatus.active.value,
                    _iso(started_at),
                    _iso(ends_at),
                ),
            )
            return conn.execute("SELECT * FROM sessions WHERE id = ?", (cursor.lastrowid,)).fetchone()

    def get_session(self, session_id: int) -> sqlite3.Row | None:
        """get_session

        Args:
            session_id: 세션 식별자.

        Returns:
            sqlite3.Row | None: 세션을 찾으면 행, 없으면 None.
        """
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if not row:
                return None
            # 조회 시점에 만료 여부를 늦게 계산해도 호출자는 항상 최신 상태를 받게 된다.
            if row["status"] == SessionStatus.active.value and _dt(row["ends_at"]) < datetime.now(UTC):
                conn.execute(
                    "UPDATE sessions SET status = ? WHERE id = ?",
                    (SessionStatus.expired.value, session_id),
                )
                row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            return row

    def complete_session(self, session_id: int, result_text: str, completed_units_delta: int) -> sqlite3.Row | None:
        """complete_session

        Args:
            session_id: 세션 식별자.
            result_text: 사용자가 보고한 결과 텍스트.
            completed_units_delta: 연결된 프로젝트에 반영할 진행량 증가분.

        Returns:
            sqlite3.Row | None: 세션을 찾으면 갱신된 행, 없으면 None.
        """
        ended_at = datetime.now(UTC)
        with self.connect() as conn:
            session = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if not session:
                return None
            conn.execute(
                """
                UPDATE sessions
                SET status = ?, ended_at = ?, reported_result = ?, completed_units_delta = ?
                WHERE id = ?
                """,
                (SessionStatus.completed.value, _iso(ended_at), result_text, completed_units_delta, session_id),
            )
            if session["project_id"] and completed_units_delta:
                # 반복 보고가 들어와도 총 작업량을 넘기지 않도록 진행량을 상한 처리한다.
                conn.execute(
                    """
                    UPDATE projects
                    SET completed_units = MIN(total_units, completed_units + ?)
                    WHERE id = ?
                    """,
                    (completed_units_delta, session["project_id"]),
                )
            return conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()

    def add_message(self, user_id: int, project_id: int | None, role: str, content: str) -> None:
        """add_message

        Args:
            user_id: 내부 사용자 식별자.
            project_id: 연결된 프로젝트 식별자. 없을 수 있다.
            role: user 또는 assistant 같은 채팅 역할.
            content: 메시지 본문.

        Returns:
            None: 메시지 행을 저장한다.
        """
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO messages (user_id, project_id, role, content, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, project_id, role, content, _iso(datetime.now(UTC))),
            )

    def recent_messages(self, user_id: int, limit: int = 8) -> list[sqlite3.Row]:
        """recent_messages

        Args:
            user_id: 내부 사용자 식별자.
            limit: 반환할 최대 행 수.

        Returns:
            list[sqlite3.Row]: 시간 순서대로 정렬된 최근 메시지 목록.
        """
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM messages
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        # 조회는 최신순이 효율적이지만, 모델 입력은 시간순이 더 자연스러워 뒤집어서 반환한다.
        return list(reversed(rows))

    def today_completed_sessions(self, user_id: int) -> list[sqlite3.Row]:
        """today_completed_sessions

        Args:
            user_id: 내부 사용자 식별자.

        Returns:
            list[sqlite3.Row]: UTC 자정 이후 완료된 세션 목록.
        """
        start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT * FROM sessions
                WHERE user_id = ? AND status = ? AND started_at >= ?
                ORDER BY started_at ASC
                """,
                (user_id, SessionStatus.completed.value, _iso(start)),
            ).fetchall()

    def has_reminder_log(self, user_id: int, reminder_type: str, reminder_date: str) -> bool:
        """has_reminder_log

        Args:
            user_id: 내부 사용자 식별자.
            reminder_type: 리마인더 종류 키.
            reminder_date: YYYY-MM-DD 날짜 키.

        Returns:
            bool: 이미 같은 리마인더가 기록됐으면 True.
        """
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT id FROM reminder_logs
                WHERE user_id = ? AND reminder_type = ? AND reminder_date = ?
                """,
                (user_id, reminder_type, reminder_date),
            ).fetchone()
            return row is not None

    def add_reminder_log(self, user_id: int, reminder_type: str, reminder_date: str) -> None:
        """add_reminder_log

        Args:
            user_id: 내부 사용자 식별자.
            reminder_type: 리마인더 종류 키.
            reminder_date: YYYY-MM-DD 날짜 키.

        Returns:
            None: 중복 방지용 리마인더 발송 기록을 저장한다.
        """
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO reminder_logs (user_id, reminder_type, reminder_date, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, reminder_type, reminder_date, _iso(datetime.now(UTC))),
            )
