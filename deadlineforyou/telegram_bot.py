from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from telegram import ReplyKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.error import TimedOut
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from deadlineforyou.config import get_settings
from deadlineforyou.providers import build_provider
from deadlineforyou.service import DeadlineCoachService
from deadlineforyou.storage import Database


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
LOGGER = logging.getLogger("deadlineforyou.telegram")

PROJECT_TEMPLATE_LABEL = "프로젝트 등록 양식"
PROJECT_UPDATE_LABEL = "프로젝트 수정 양식"
PROJECT_DELETE_LABEL = "프로젝트 삭제 양식"
PROJECT_LIST_LABEL = "프로젝트 목록"
PROJECT_SWITCH_LABEL = "프로젝트 전환 양식"
STATUS_LABEL = "현재 상태"
HELP_LABEL = "도움말"
TIMER_TEMPLATE_LABEL = "타이머 시작 양식"
REPORT_LABEL = "작업 보고 안내"
TRANSLATE_TEMPLATE_LABEL = "번역 양식"
IMAGE_TEMPLATE_LABEL = "이미지 양식"
FILE_ASSIST_TEMPLATE_LABEL = "파일 번역 보조 양식"

SUPPORTED_LANGUAGE_CODES = {"ko", "jp", "en", "ch"}
LANGUAGE_HELP_TEXT = "지원 언어 코드는 ko, jp, en, ch만 쓴다."


TELEGRAM_READ_TIMEOUT_SECONDS = 120
TELEGRAM_WRITE_TIMEOUT_SECONDS = 120
TELEGRAM_CONNECT_TIMEOUT_SECONDS = 30
TELEGRAM_POOL_TIMEOUT_SECONDS = 30
CHECKIN_HOURS = (10, 15, 21)


def _sanitize_coach_text(text: str, max_lines: int = 5) -> str:
    """_sanitize_coach_text

    Args:
        text: 모델이 생성한 원문 문자열.
        max_lines: 허용할 최대 줄 수.

    Returns:
        str: 텔레그램 출력용으로 정리된 문자열.
    """
    cleaned = text.replace("*", "").replace("_", "")
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    if not lines:
        return "지금 상태를 한 줄로 다시 보내라."
    return "\n".join(lines[:max_lines])


def build_service() -> DeadlineCoachService:
    """build_service

    Args:
        없음.

    Returns:
        DeadlineCoachService: 텔레그램 봇이 재사용할 서비스 인스턴스.
    """
    settings = get_settings()
    database = Database(settings.database_path)
    provider = build_provider(settings)
    return DeadlineCoachService(database, provider)


def _telegram_platform_id(update: Update) -> str:
    """_telegram_platform_id

    Args:
        update: 텔레그램 업데이트 객체.

    Returns:
        str: 내부 저장에 사용할 텔레그램 사용자 식별자 문자열.
    """
    return f"telegram-{update.effective_user.id}"


def _display_name(update: Update) -> str:
    """_display_name

    Args:
        update: 텔레그램 업데이트 객체.

    Returns:
        str: 저장용 닉네임 문자열.
    """
    user = update.effective_user
    if user.username:
        return user.username
    if user.full_name:
        return user.full_name
    return f"user-{user.id}"


async def _ensure_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> dict:
    """_ensure_user

    Args:
        update: 텔레그램 업데이트 객체.
        context: 텔레그램 핸들러 컨텍스트.

    Returns:
        dict: 현재 업데이트를 보낸 사용자 레코드.
    """
    service: DeadlineCoachService = context.application.bot_data["service"]
    return service.get_or_create_user(
        platform_user_id=_telegram_platform_id(update),
        nickname=_display_name(update),
    )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """start_command

    Args:
        update: 텔레그램 업데이트 객체.
        context: 텔레그램 핸들러 컨텍스트.

    Returns:
        None: 시작 안내 메시지를 전송한다.
    """
    user = await _ensure_user(update, context)
    LOGGER.info("start_command user_id=%s chat_id=%s", user["id"], update.effective_chat.id)
    keyboard = ReplyKeyboardMarkup(
        [
            [PROJECT_TEMPLATE_LABEL, PROJECT_UPDATE_LABEL],
            [PROJECT_DELETE_LABEL, PROJECT_LIST_LABEL],
            [PROJECT_SWITCH_LABEL, STATUS_LABEL],
            [TIMER_TEMPLATE_LABEL, REPORT_LABEL],
            [TRANSLATE_TEMPLATE_LABEL, IMAGE_TEMPLATE_LABEL],
            [FILE_ASSIST_TEMPLATE_LABEL, HELP_LABEL],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        selective=True,
    )
    await update.message.reply_text(
        "\n".join(
            [
                "마감 집행관 「締切監督」 투입.",
                f"사용자 등록 완료: {user['nickname']}",
                "",
                "처음 쓰는 사람은 이 순서만 따라오면 된다.",
                "",
                "1. 프로젝트 등록",
                "예:",
                "게임 시나리오 번역 | jp | ko | auto | 2026-03-14 18:00 | 문장",
                "",
                "2. 상태 확인",
                "/status 또는 현재 상태 버튼",
                "",
                "3. 작업 시작",
                "/timer 25",
                "",
                "4. 세션 끝나면 보고",
                "/report 12",
                "",
                "설명:",
                "- 프로젝트 등록의 시간은 작업 시간이 아니라 마감 시각이다.",
                "- 총량을 아직 모르겠으면 auto 로 두고 파일을 올리면 된다.",
                "- 활성 프로젝트가 있으면 .txt 파일을 그냥 올려도 된다.",
                "- 파일을 올리면 글자 수와 세그먼트 수를 자동 계산한다.",
                "",
                "직접 명령:",
                "- 번역: /translate jp | en | 締切は明日の18時です。",
                "- 이미지: /image happy hamster, clean illustration",
                "- 파일 번역 보조: /file_assist 3 | jp | ko",
                "- /file_assist 는 현재 파일 앞부분 최대 1500자만 번역한다.",
                "",
                LANGUAGE_HELP_TEXT,
                "더 자세한 설명은 /help",
            ]
        ),
        reply_markup=keyboard,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """help_command

    Args:
        update: 텔레그램 업데이트 객체.
        context: 텔레그램 핸들러 컨텍스트.

    Returns:
        None: 사용 가능한 명령 목록을 전송한다.
    """
    del context
    LOGGER.info("help_command chat_id=%s", update.effective_chat.id)
    await update.message.reply_text(
        "\n".join(
            [
                "텔레그램에서 실제로 쓰는 순서:",
                "",
                "1. 프로젝트를 등록한다.",
                "예:",
                "게임 시나리오 번역 | jp | ko | auto | 2026-03-14 18:00 | 문장",
                "",
                "2. /status 로 현재 프로젝트를 확인한다.",
                "",
                "3. /timer 25 로 작업 세션을 시작한다.",
                "",
                "4. 세션이 끝나면 /report 12 같이 숫자로 완료량을 보낸다.",
                "",
                "5. 필요하면 .txt 파일을 올려 파일 단위로 관리한다.",
                "",
                "6. 필요하면 /translate, /image, /file_assist 를 쓴다.",
                "",
                "명령 상세 설명:",
                "",
                "/start",
                "시작 안내와 사용자 등록",
                "",
                "/deadline_add <제목> | <원문 언어> | <목표 언어> | <총량> | <YYYY-MM-DD HH:MM> | <단위>",
                "프로젝트 등록",
                "여기서 시간은 작업 시간 아니라 마감 시각이다.",
                "총량은 프로젝트 전체 분량이다. 이번 세션 분량이 아니다.",
                "총량을 아직 모르겠으면 auto 로 넣어도 된다. 파일을 올리면 자동 집계로 다시 계산된다.",
                "단위는 문장, 페이지, 줄 같은 작업 단위명이다.",
                "예: /deadline_add 게임 시나리오 번역 | jp | ko | 120 | 2026-03-14 18:00 | 문장",
                "예: /deadline_add 게임 시나리오 번역 | jp | ko | auto | 2026-03-14 18:00 | 문장",
                "또는 명령 없이",
                "게임 시나리오 번역 | jp | ko | 120 | 2026-03-14 18:00 | 문장",
                "게임 시나리오 번역 | jp | ko | auto | 2026-03-14 18:00 | 문장",
                LANGUAGE_HELP_TEXT,
                "",
                "/deadline_list",
                "프로젝트 목록 확인",
                "프로젝트 ID, 남은 파일 수, 밀린 파일 수까지 같이 본다.",
                "",
                "/deadline_switch <프로젝트ID>",
                "활성 프로젝트 전환",
                "예: /deadline_switch 3",
                "",
                "/deadline_update <프로젝트ID> | <제목> | <원문언어> | <목표언어> | <총량> | <YYYY-MM-DD HH:MM> | <단위>",
                "프로젝트 정보 수정",
                "예: /deadline_update 3 | 게임 시나리오 번역 수정본 | jp | ko | auto | 2026-03-15 18:00 | 문장",
                "",
                "/deadline_delete <프로젝트ID>",
                "프로젝트 삭제",
                "예: /deadline_delete 3",
                "",
                "/status",
                "현재 활성 프로젝트와 오늘 진행 상황 확인",
                "지금 어떤 프로젝트가 활성인지, 오늘 몇 분 했는지, 남은 파일이 몇 개인지 본다.",
                "하루 최소 몇 단위 해야 하는지도 같이 본다.",
                "",
                "/timer <분>",
                "원하는 분 수로 타이머 세션 시작",
                "예: /timer 10, /timer 25, /timer 45",
                "10분 이상이면 10분마다 압박 메시지가 온다.",
                "끝나면 /report <작업량> 으로 숫자 보고를 해야 한다.",
                "예: 이번 세션에서 8문장을 끝냈으면 /report 8",
                "보고를 안 하면 세션은 0으로 자동 마감되고 다시 /timer 를 시작하라고 재촉한다.",
                "",
                "/report <숫자>",
                "방금 끝낸 작업량 보고",
                "예: /report 12",
                "숫자가 없으면 반영되지 않는다.",
                "여기 숫자는 이번 세션에서 실제로 끝낸 양만 넣는다.",
                "예: 이번 25분 동안 12문장을 끝냈으면 /report 12",
                "",
                "/translate <원문언어> | <목표언어> | <원문>",
                "짧은 텍스트 번역",
                "예: /translate jp | en | 締切は明日の18時です。",
                LANGUAGE_HELP_TEXT,
                "",
                "/image <프롬프트>",
                "프롬프트 기반 이미지 생성",
                "예: /image deadline enforcer poster, black and orange warning stripes",
                "",
                "파일 업로드",
                "활성 프로젝트가 있으면 .txt 파일을 그냥 올려도 파일 단위 작업으로 등록된다.",
                "파일을 올리면 문장 수, 글자 수, 세그먼트 수를 자동 계산한다.",
                "업로드 후 파일 ID를 알려준다.",
                "",
                "/file_assist <파일ID> | <원문언어> | <목표언어>",
                "업로드한 파일의 앞부분 최대 1500자를 번역 보조한다.",
                "결과는 텍스트 메시지가 아니라 .txt 파일로 돌려준다.",
                "예: /file_assist 3 | jp | ko",
                "",
                "버튼 설명:",
                f"- {PROJECT_TEMPLATE_LABEL}: 프로젝트 등록 예시 출력",
                f"- {PROJECT_UPDATE_LABEL}: 프로젝트 수정 예시 출력",
                f"- {PROJECT_DELETE_LABEL}: 프로젝트 삭제 예시 출력",
                f"- {PROJECT_LIST_LABEL}: 프로젝트 목록 바로 조회",
                f"- {PROJECT_SWITCH_LABEL}: 프로젝트 전환 예시 출력",
                f"- {STATUS_LABEL}: 현재 활성 프로젝트 상태 바로 조회",
                f"- {REPORT_LABEL}: /report 사용 예시 출력",
                f"- {TIMER_TEMPLATE_LABEL}: /timer 예시 출력",
                f"- {TRANSLATE_TEMPLATE_LABEL}: /translate 예시 출력",
                f"- {IMAGE_TEMPLATE_LABEL}: /image 예시 출력",
                f"- {FILE_ASSIST_TEMPLATE_LABEL}: /file_assist 예시 출력",
                f"- {HELP_LABEL}: 이 도움말 다시 보기",
                "",
                "평문 메시지 예시:",
                "하기 싫다",
                "마감 4시간 전인데 절반 남음",
            ]
        )
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """status_command

    Args:
        update: 텔레그램 업데이트 객체.
        context: 텔레그램 핸들러 컨텍스트.

    Returns:
        None: 현재 활성 프로젝트와 리포트 요약을 전송한다.
    """
    user = await _ensure_user(update, context)
    LOGGER.info("status_command user_id=%s", user["id"])
    service: DeadlineCoachService = context.application.bot_data["service"]
    projects = service.list_projects(user["id"])
    if not projects:
        await update.message.reply_text(
            "\n".join(
                [
                    "아직 등록된 프로젝트가 없다.",
                    "아래 형식으로 한 줄만 보내면 된다.",
                    "게임 시나리오 번역 | jp | ko | auto | 2026-03-14 18:00 | 문장",
                    "뜻: 제목 | 원문언어 | 목표언어 | 총량 또는 auto | 마감시각 | 단위",
                    "전체 설명은 /help",
                ]
            )
        )
        return

    project = next((item for item in projects if item["status"] == "active"), projects[0])
    report = service.build_daily_report(user["id"])
    overview = service.build_project_overview(project["id"])
    project_files = service.list_project_files(project["id"])
    pending_files = [file_row for file_row in project_files if file_row["translated_segments"] < file_row["source_segments"]]
    file_lines: list[str] = []
    if pending_files:
        file_lines.append("파일 ID 목록:")
        for file_row in pending_files[:5]:
            file_lines.append(
                f"- ID {file_row['id']} | {file_row['name']} | "
                f"{file_row['translated_segments']}/{file_row['source_segments']} 세그먼트"
            )
    elif project_files:
        file_lines.append("파일 ID 목록:")
        for file_row in project_files[:5]:
            file_lines.append(
                f"- ID {file_row['id']} | {file_row['name']} | "
                f"{file_row['translated_segments']}/{file_row['source_segments']} 세그먼트"
            )

    await update.message.reply_text(
        "\n".join(
            [
                f"프로젝트: {project['title']}",
                f"언어: {project['source_language']} -> {project['target_language']}",
                f"진행률: {project['completed_units']}/{project['total_units']} {project['unit_label']}",
                f"파일: 남은 {overview['remaining_file_count']}개 / 전체 {overview['file_count']}개 / 밀린 파일 {overview['delayed_file_count']}개",
                f"자동 집계: {overview['translated_segments']}/{overview['total_segments']} 세그먼트, {overview['translated_chars']}/{overview['total_chars']}자",
                f"마감: {project['deadline_at']}",
                f"플래너: {overview['planner']['summary']}",
                f"오늘 집중: {report['focus_minutes']}분",
                f"오늘 완료량: {report['completed_units']}",
                *file_lines,
            ]
        )
    )


def _parse_deadline_input(raw_text: str, timezone_name: str) -> tuple[str, str, str, int, datetime, str]:
    """_parse_deadline_input

    Args:
        raw_text: `/deadline_add` 뒤에 입력된 원문.
        timezone_name: 사용자 시간대 이름.

    Returns:
        tuple[str, str, str, int, datetime, str]: 제목, 원문 언어, 목표 언어, 총량, 마감 시각, 단위명.
    """
    parts = [part.strip() for part in raw_text.split("|")]
    if len(parts) < 5:
        raise ValueError("입력 형식이 부족하다.")

    title = parts[0]
    source_language = _normalize_language_code(parts[1])
    target_language = _normalize_language_code(parts[2])
    total_units_token = parts[3].strip().lower()
    total_units = 1 if total_units_token in {"auto", "?", ""} else int(parts[3])
    deadline_str = parts[4]
    unit_label = parts[5] if len(parts) >= 6 and parts[5] else "문장"

    # 시간대가 없는 입력은 사용자의 기본 시간대로 해석한다.
    deadline_at = datetime.fromisoformat(deadline_str.replace(" ", "T"))
    if deadline_at.tzinfo is None:
        deadline_at = deadline_at.replace(tzinfo=ZoneInfo(timezone_name))
    _validate_supported_language(source_language)
    _validate_supported_language(target_language)
    return title, source_language, target_language, total_units, deadline_at, unit_label


def _normalize_language_code(value: str) -> str:
    """_normalize_language_code

    Args:
        value: 입력된 언어 코드 문자열.

    Returns:
        str: 정규화된 언어 코드.
    """
    normalized = value.strip().lower()
    aliases = {
        "ja": "jp",
        "zh": "ch",
        "cn": "ch",
    }
    return aliases.get(normalized, normalized)


def _validate_supported_language(value: str) -> None:
    """_validate_supported_language

    Args:
        value: 검증할 언어 코드 문자열.

    Returns:
        None: 지원 언어가 아니면 예외를 발생시킨다.
    """
    if value not in SUPPORTED_LANGUAGE_CODES:
        raise ValueError(LANGUAGE_HELP_TEXT)


def _looks_like_project_input(text: str) -> bool:
    """_looks_like_project_input

    Args:
        text: 사용자가 보낸 일반 텍스트.

    Returns:
        bool: 프로젝트 등록 형식처럼 보이면 True.
    """
    return text.count("|") >= 4 and not text.startswith("/")


def _looks_like_translation_request(text: str) -> bool:
    """_looks_like_translation_request

    Args:
        text: 사용자가 보낸 일반 텍스트.

    Returns:
        bool: 번역 요청처럼 보이면 True.
    """
    lowered = text.lower()
    return "번역" in text or "/translate" in lowered


def _looks_like_image_request(text: str) -> bool:
    """_looks_like_image_request

    Args:
        text: 사용자가 보낸 일반 텍스트.

    Returns:
        bool: 이미지 생성 요청처럼 보이면 True.
    """
    return "이미지" in text and ("생성" in text or "만들" in text)


async def _create_project_from_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    raw_text: str,
    user: dict,
) -> bool:
    """_create_project_from_text

    Args:
        update: 텔레그램 업데이트 객체.
        context: 텔레그램 핸들러 컨텍스트.
        raw_text: 프로젝트 등록 후보 문자열.
        user: 현재 사용자 레코드.

    Returns:
        bool: 프로젝트 등록 처리까지 끝냈으면 True.
    """
    service: DeadlineCoachService = context.application.bot_data["service"]
    try:
        title, source_language, target_language, total_units, deadline_at, unit_label = _parse_deadline_input(
            raw_text,
            user["timezone"],
        )
    except ValueError:
        return False

    for project in service.list_projects(user["id"]):
        if project["status"] == "active":
            service.update_project(project["id"], {"status": "paused"})

    project = service.create_project(
        {
            "user_id": user["id"],
            "title": title,
            "source_language": source_language,
            "target_language": target_language,
            "total_units": total_units,
            "completed_units": 0,
            "deadline_at": deadline_at,
            "unit_label": unit_label,
        }
    )

    await update.message.reply_text(
        "\n".join(
            [
                "프로젝트 등록 완료.",
                f"제목: {project['title']}",
                f"언어: {project['source_language']} -> {project['target_language']}",
                f"분량: {project['completed_units']}/{project['total_units']} {project['unit_label']}",
                f"마감: {project['deadline_at']}",
                "다음 순서:",
                "1. /status 로 다시 확인",
                "2. /timer 25 로 작업 시작",
                "3. 끝나면 /report <작업량> 으로 숫자 보고",
            ]
        )
    )
    return True


async def deadline_add_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """deadline_add_command

    Args:
        update: 텔레그램 업데이트 객체.
        context: 텔레그램 핸들러 컨텍스트.

    Returns:
        None: 새 프로젝트를 등록하고 활성 프로젝트로 안내한다.
    """
    user = await _ensure_user(update, context)
    LOGGER.info("deadline_add_command user_id=%s raw_text=%s", user["id"], update.message.text)
    service: DeadlineCoachService = context.application.bot_data["service"]

    raw_text = update.message.text.removeprefix("/deadline_add").strip()
    if not raw_text:
        await update.message.reply_text(
            "\n".join(
                [
                    "프로젝트 정보가 비어 있다.",
                    "프로젝트는 아래 두 방식 중 하나로 등록하면 된다.",
                    "/deadline_add 게임 시나리오 번역 | jp | ko | 120 | 2026-03-14 18:00 | 문장",
                    "게임 시나리오 번역 | jp | ko | 120 | 2026-03-14 18:00 | 문장",
                    "형식 뜻: 제목 | 원문언어 | 목표언어 | 총량 | 마감시각 | 단위",
                    LANGUAGE_HELP_TEXT,
                    "전체 설명은 /help",
                ]
            )
        )
        return

    try:
        title, source_language, target_language, total_units, deadline_at, unit_label = _parse_deadline_input(
            raw_text,
            user["timezone"],
        )
    except ValueError:
        await update.message.reply_text(
            "\n".join(
                [
                    "형식이 맞지 않는다.",
                    "형식은 제목 | 원문언어 | 목표언어 | 총량 | 마감시각 | 단위 순서다.",
                    "총량을 아직 모르겠으면 auto 를 써도 된다.",
                    "예시:",
                    "/deadline_add 게임 시나리오 번역 | jp | ko | 120 | 2026-03-14 18:00 | 문장",
                    "또는",
                    "게임 시나리오 번역 | jp | ko | 120 | 2026-03-14 18:00 | 문장",
                    LANGUAGE_HELP_TEXT,
                    "전체 설명은 /help",
                ]
            )
        )
        return

    # 새 프로젝트를 활성으로 쓰기 위해 기존 active 프로젝트를 paused로 내려둔다.
    for project in service.list_projects(user["id"]):
        if project["status"] == "active":
            service.update_project(project["id"], {"status": "paused"})

    project = service.create_project(
        {
            "user_id": user["id"],
            "title": title,
            "source_language": source_language,
            "target_language": target_language,
            "total_units": total_units,
            "completed_units": 0,
            "deadline_at": deadline_at,
            "unit_label": unit_label,
        }
    )

    await update.message.reply_text(
        "\n".join(
            [
                "프로젝트 등록 완료.",
                f"제목: {project['title']}",
                f"언어: {project['source_language']} -> {project['target_language']}",
                f"분량: {project['completed_units']}/{project['total_units']} {project['unit_label']}",
                f"마감: {project['deadline_at']}",
                "",
                "다음 순서:",
                "1. /status 로 지금 프로젝트가 활성인지 확인",
                "2. /timer 25 로 작업 시작",
                "3. 끝나면 /report <작업량> 으로 숫자 보고",
            ]
        )
    )


async def deadline_update_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """deadline_update_command

    Args:
        update: 텔레그램 업데이트 객체.
        context: 텔레그램 핸들러 컨텍스트.

    Returns:
        None: 기존 프로젝트 정보를 수정한다.
    """
    user = await _ensure_user(update, context)
    LOGGER.info("deadline_update_command user_id=%s raw_text=%s", user["id"], update.message.text)
    service: DeadlineCoachService = context.application.bot_data["service"]
    raw_text = update.message.text.removeprefix("/deadline_update").strip()
    if not raw_text:
        await update.message.reply_text(
            "\n".join(
                [
                    "수정할 프로젝트 정보가 비어 있다.",
                    "/deadline_update 3 | 게임 시나리오 번역 수정본 | jp | ko | auto | 2026-03-15 18:00 | 문장",
                    "먼저 /deadline_list 로 프로젝트 ID를 확인해라.",
                    "전체 설명은 /help",
                ]
            )
        )
        return

    try:
        project_id, title, source_language, target_language, total_units, deadline_at, unit_label = _parse_deadline_update_input(
            raw_text,
            user["timezone"],
        )
    except ValueError:
        await update.message.reply_text(
            "\n".join(
                [
                    "수정 형식이 맞지 않는다.",
                    "/deadline_update <프로젝트ID> | <제목> | <원문언어> | <목표언어> | <총량> | <마감시각> | <단위>",
                    "예: /deadline_update 3 | 게임 시나리오 번역 수정본 | jp | ko | auto | 2026-03-15 18:00 | 문장",
                    "전체 설명은 /help",
                ]
            )
        )
        return

    projects = service.list_projects(user["id"])
    project = next((item for item in projects if item["id"] == project_id), None)
    if not project:
        await update.message.reply_text("그 프로젝트 ID는 네 목록에 없다. /deadline_list 로 다시 확인해라.")
        return

    updated = service.update_project(
        project_id,
        {
            "title": title,
            "source_language": source_language,
            "target_language": target_language,
            "total_units": total_units,
            "deadline_at": deadline_at,
            "unit_label": unit_label,
        },
    )
    await update.message.reply_text(
        "\n".join(
            [
                "프로젝트 수정 완료.",
                f"ID: {updated['id']}",
                f"제목: {updated['title']}",
                f"언어: {updated['source_language']} -> {updated['target_language']}",
                f"분량: {updated['completed_units']}/{updated['total_units']} {updated['unit_label']}",
                f"마감: {updated['deadline_at']}",
            ]
        )
    )


async def deadline_delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """deadline_delete_command

    Args:
        update: 텔레그램 업데이트 객체.
        context: 텔레그램 핸들러 컨텍스트.

    Returns:
        None: 프로젝트와 연결된 데이터를 삭제한다.
    """
    user = await _ensure_user(update, context)
    LOGGER.info("deadline_delete_command user_id=%s args=%s", user["id"], context.args)
    service: DeadlineCoachService = context.application.bot_data["service"]
    if not context.args:
        await update.message.reply_text(
            "\n".join(
                [
                    "삭제할 프로젝트 ID가 필요하다.",
                    "예: /deadline_delete 3",
                    "프로젝트 ID는 /deadline_list 에서 확인한다.",
                ]
            )
        )
        return

    try:
        project_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("프로젝트 ID는 숫자로 넣어라. 예: /deadline_delete 3")
        return

    projects = service.list_projects(user["id"])
    project = next((item for item in projects if item["id"] == project_id), None)
    if not project:
        await update.message.reply_text("그 프로젝트 ID는 네 목록에 없다. /deadline_list 로 다시 확인해라.")
        return

    deleted = service.delete_project(project_id)
    if not deleted:
        await update.message.reply_text("프로젝트를 찾지 못했다.")
        return

    context.user_data.pop("last_session_id", None)
    await update.message.reply_text(
        "\n".join(
            [
                "프로젝트 삭제 완료.",
                f"삭제한 프로젝트: {deleted['title']}",
                "연결된 파일, 세션, 메시지도 같이 지웠다.",
                "남은 프로젝트는 /deadline_list 로 다시 확인해라.",
            ]
        )
    )


async def deadline_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """deadline_list_command

    Args:
        update: 텔레그램 업데이트 객체.
        context: 텔레그램 핸들러 컨텍스트.

    Returns:
        None: 현재 사용자의 프로젝트 목록을 전송한다.
    """
    user = await _ensure_user(update, context)
    LOGGER.info("deadline_list_command user_id=%s", user["id"])
    service: DeadlineCoachService = context.application.bot_data["service"]
    projects = service.list_projects(user["id"])
    if not projects:
        await update.message.reply_text("등록된 프로젝트가 없다. /deadline_add부터 쳐라.")
        return

    lines = ["현재 프로젝트 목록:"]
    for project in projects[:10]:
        overview = service.build_project_overview(project["id"])
        lines.append(
            f"- ID {project['id']} | [{project['status']}] {project['title']} | "
            f"{project['source_language']}->{project['target_language']} | "
            f"{project['completed_units']}/{project['total_units']} {project['unit_label']} | "
            f"남은 파일 {overview['remaining_file_count']}개 | "
            f"밀린 파일 {overview['delayed_file_count']}개 | "
            f"{project['deadline_at']}"
        )
    await update.message.reply_text("\n".join(lines))


async def deadline_switch_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """deadline_switch_command

    Args:
        update: 텔레그램 업데이트 객체.
        context: 텔레그램 핸들러 컨텍스트.

    Returns:
        None: 사용자가 고른 프로젝트를 활성 프로젝트로 전환한다.
    """
    user = await _ensure_user(update, context)
    LOGGER.info("deadline_switch_command user_id=%s args=%s", user["id"], context.args)
    service: DeadlineCoachService = context.application.bot_data["service"]
    if not context.args:
        await update.message.reply_text(
            "\n".join(
                [
                    "전환할 프로젝트 ID가 필요하다.",
                    "예: /deadline_switch 3",
                    "프로젝트 ID는 /deadline_list 에서 확인한다.",
                ]
            )
        )
        return

    try:
        target_project_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("프로젝트 ID는 숫자로 넣어라. 예: /deadline_switch 3")
        return

    projects = service.list_projects(user["id"])
    target_project = next((project for project in projects if project["id"] == target_project_id), None)
    if not target_project:
        await update.message.reply_text("그 프로젝트 ID는 네 목록에 없다. /deadline_list 로 다시 확인해라.")
        return

    for project in projects:
        new_status = "active" if project["id"] == target_project_id else "paused"
        if project["status"] != new_status:
            service.update_project(project["id"], {"status": new_status})

    refreshed = next(project for project in service.list_projects(user["id"]) if project["id"] == target_project_id)
    await update.message.reply_text(
        "\n".join(
            [
                "활성 프로젝트 전환 완료.",
                f"ID: {refreshed['id']}",
                f"제목: {refreshed['title']}",
                f"언어: {refreshed['source_language']} -> {refreshed['target_language']}",
                f"마감: {refreshed['deadline_at']}",
                "이제 파일 업로드와 /timer 는 이 프로젝트 기준으로 동작한다.",
            ]
        )
    )


async def project_template_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """project_template_message

    Args:
        update: 텔레그램 업데이트 객체.
        context: 텔레그램 핸들러 컨텍스트.

    Returns:
        None: 프로젝트 등록용 간단한 입력 예시를 전송한다.
    """
    user = await _ensure_user(update, context)
    LOGGER.info("project_template_message user_id=%s", user["id"])
    await update.message.reply_text(
        "\n".join(
            [
                "프로젝트 등록은 아래 줄 한 줄만 보내면 된다.",
                "/deadline_add 게임 시나리오 번역 | jp | ko | 120 | 2026-03-14 18:00 | 문장",
                "총량을 모르겠으면 120 대신 auto 로 넣어도 된다.",
                "또는 /deadline_add 없이",
                "게임 시나리오 번역 | jp | ko | 120 | 2026-03-14 18:00 | 문장",
                "형식 뜻:",
                "제목 | 원문언어 | 목표언어 | 총량 | 마감시각 | 단위",
                "총량은 auto 가능. 파일을 올리면 다시 자동 계산된다.",
                "예: 게임 시나리오 번역 | jp | ko | 120 | 2026-03-14 18:00 | 문장",
                LANGUAGE_HELP_TEXT,
                "자세한 설명은 /help",
            ]
        )
    )


async def project_update_template_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """project_update_template_message

    Args:
        update: 텔레그램 업데이트 객체.
        context: 텔레그램 핸들러 컨텍스트.

    Returns:
        None: 프로젝트 수정 명령 예시를 전송한다.
    """
    user = await _ensure_user(update, context)
    LOGGER.info("project_update_template_message user_id=%s", user["id"])
    await update.message.reply_text(
        "\n".join(
            [
                "먼저 프로젝트 목록에서 ID를 확인한 뒤 아래처럼 보내라.",
                "/deadline_list",
                "/deadline_update 3 | 게임 시나리오 번역 수정본 | jp | ko | auto | 2026-03-15 18:00 | 문장",
                "형식: 프로젝트ID | 제목 | 원문언어 | 목표언어 | 총량 | 마감시각 | 단위",
                "자세한 설명은 /help",
            ]
        )
    )


async def project_delete_template_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """project_delete_template_message

    Args:
        update: 텔레그램 업데이트 객체.
        context: 텔레그램 핸들러 컨텍스트.

    Returns:
        None: 프로젝트 삭제 명령 예시를 전송한다.
    """
    user = await _ensure_user(update, context)
    LOGGER.info("project_delete_template_message user_id=%s", user["id"])
    await update.message.reply_text(
        "\n".join(
            [
                "먼저 프로젝트 목록에서 ID를 확인한 뒤 아래처럼 보내라.",
                "/deadline_list",
                "/deadline_delete 3",
                "지우면 연결된 파일, 세션, 메시지도 같이 지워진다.",
                "자세한 설명은 /help",
            ]
        )
    )


async def translate_template_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """translate_template_message

    Args:
        update: 텔레그램 업데이트 객체.
        context: 텔레그램 핸들러 컨텍스트.

    Returns:
        None: 번역 명령용 간단한 입력 예시를 전송한다.
    """
    user = await _ensure_user(update, context)
    LOGGER.info("translate_template_message user_id=%s", user["id"])
    await update.message.reply_text(
        "\n".join(
            [
                "아래 줄을 복사해서 언어와 원문만 바꿔서 보내라.",
                "/translate jp | en | 締切は明日の18時です。",
                LANGUAGE_HELP_TEXT,
                "자세한 설명은 /help",
            ]
        )
    )


def _parse_translate_command_input(raw_text: str) -> tuple[str, str, str]:
    """_parse_translate_command_input

    Args:
        raw_text: `/translate` 뒤에 입력된 원문.

    Returns:
        tuple[str, str, str]: 원문 언어, 목표 언어, 원문 텍스트.
    """
    parts = [part.strip() for part in raw_text.split("|", maxsplit=2)]
    if len(parts) != 3:
        raise ValueError("번역 형식이 맞지 않는다.")

    source_language = _normalize_language_code(parts[0])
    target_language = _normalize_language_code(parts[1])
    text = parts[2].strip()
    if not text:
        raise ValueError("번역할 원문이 비어 있다.")

    _validate_supported_language(source_language)
    _validate_supported_language(target_language)
    return source_language, target_language, text


def _parse_deadline_update_input(raw_text: str, timezone_name: str) -> tuple[int, str, str, str, int, datetime, str]:
    """_parse_deadline_update_input

    Args:
        raw_text: `/deadline_update` 뒤에 입력된 원문.
        timezone_name: 사용자 시간대 이름.

    Returns:
        tuple[int, str, str, str, int, datetime, str]: 프로젝트 ID, 제목, 언어, 총량, 마감, 단위.
    """
    parts = [part.strip() for part in raw_text.split("|")]
    if len(parts) < 6:
        raise ValueError("수정 형식이 부족하다.")

    project_id = int(parts[0])
    parsed = _parse_deadline_input(" | ".join(parts[1:]), timezone_name)
    title, source_language, target_language, total_units, deadline_at, unit_label = parsed
    return project_id, title, source_language, target_language, total_units, deadline_at, unit_label


async def timer_template_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """timer_template_message

    Args:
        update: 텔레그램 업데이트 객체.
        context: 텔레그램 핸들러 컨텍스트.

    Returns:
        None: 타이머 시작용 간단한 입력 예시를 전송한다.
    """
    user = await _ensure_user(update, context)
    LOGGER.info("timer_template_message user_id=%s", user["id"])
    await update.message.reply_text(
        "\n".join(
            [
                "타이머는 아래처럼 분 수만 넣어서 보내면 된다.",
                "/timer 25",
                "예: /timer 10, /timer 25, /timer 45",
                "이 숫자는 프로젝트 마감 시간이 아니라 이번 작업 세션 길이다.",
                "10분 이상이면 10분마다 압박 메시지가 온다.",
                "끝나면 /report <작업량> 으로 숫자 보고를 해야 한다.",
                "자세한 설명은 /help",
            ]
        )
    )


async def image_template_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """image_template_message

    Args:
        update: 텔레그램 업데이트 객체.
        context: 텔레그램 핸들러 컨텍스트.

    Returns:
        None: 이미지 생성 명령용 간단한 입력 예시를 전송한다.
    """
    user = await _ensure_user(update, context)
    LOGGER.info("image_template_message user_id=%s", user["id"])
    await update.message.reply_text(
        "\n".join(
            [
                "아래 줄을 복사해서 프롬프트만 바꿔서 보내라.",
                "/image deadline enforcer poster, black and orange warning stripes",
                "자세한 설명은 /help",
            ]
        )
    )


async def project_switch_template_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """project_switch_template_message

    Args:
        update: 텔레그램 업데이트 객체.
        context: 텔레그램 핸들러 컨텍스트.

    Returns:
        None: 프로젝트 전환 명령 예시를 전송한다.
    """
    user = await _ensure_user(update, context)
    LOGGER.info("project_switch_template_message user_id=%s", user["id"])
    await update.message.reply_text(
        "\n".join(
            [
                "프로젝트 전환은 먼저 프로젝트 목록에서 ID를 보고, 그 다음 아래처럼 보내면 된다.",
                "/deadline_list",
                "/deadline_switch 3",
                "자세한 설명은 /help",
            ]
        )
    )


async def report_template_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """report_template_message

    Args:
        update: 텔레그램 업데이트 객체.
        context: 텔레그램 핸들러 컨텍스트.

    Returns:
        None: 작업 보고 예시를 전송한다.
    """
    user = await _ensure_user(update, context)
    LOGGER.info("report_template_message user_id=%s", user["id"])
    await update.message.reply_text(
        "\n".join(
            [
                "세션이 끝나면 아래처럼 완료량 숫자만 보내면 된다.",
                "/report 12",
                "예: 이번 세션에서 12문장을 끝냈으면 /report 12",
                "자세한 설명은 /help",
            ]
        )
    )


async def file_assist_template_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """file_assist_template_message

    Args:
        update: 텔레그램 업데이트 객체.
        context: 텔레그램 핸들러 컨텍스트.

    Returns:
        None: 파일 번역 보조 명령 예시를 전송한다.
    """
    user = await _ensure_user(update, context)
    LOGGER.info("file_assist_template_message user_id=%s", user["id"])
    await update.message.reply_text(
        "\n".join(
            [
                "파일을 먼저 올려서 파일 ID를 확인한 뒤 아래처럼 보내라.",
                "/file_assist 3 | jp | ko",
                "현재는 파일 전체가 아니라 앞부분 최대 1500자만 번역한다.",
                "결과는 채팅 장문이 아니라 .txt 파일로 온다.",
                "자세한 설명은 /help",
            ]
        )
    )


def _parse_file_assist_input(raw_text: str) -> tuple[int, str, str]:
    """_parse_file_assist_input

    Args:
        raw_text: `/file_assist` 뒤에 입력된 원문.

    Returns:
        tuple[int, str, str]: 파일 식별자, 원문 언어, 목표 언어.
    """
    parts = [part.strip() for part in raw_text.split("|", maxsplit=2)]
    if len(parts) != 3:
        raise ValueError("파일 번역 보조 형식이 맞지 않는다.")
    file_id = int(parts[0])
    source_language = _normalize_language_code(parts[1])
    target_language = _normalize_language_code(parts[2])
    _validate_supported_language(source_language)
    _validate_supported_language(target_language)
    return file_id, source_language, target_language


async def translate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """translate_command

    Args:
        update: 텔레그램 업데이트 객체.
        context: 텔레그램 핸들러 컨텍스트.

    Returns:
        None: 텔레그램 입력을 번역해 결과를 전송한다.
    """
    await _ensure_user(update, context)
    LOGGER.info("translate_command chat_id=%s raw_text=%s", update.effective_chat.id, update.message.text)
    service: DeadlineCoachService = context.application.bot_data["service"]
    raw_text = update.message.text.removeprefix("/translate").strip()
    if not raw_text:
        await update.message.reply_text(
            "\n".join(
                [
                    "번역 정보가 비어 있다.",
                    "형식:",
                    "/translate <원문언어> | <목표언어> | <원문>",
                    "예시:",
                    "/translate jp | en | 締切は明日の18時です。",
                    LANGUAGE_HELP_TEXT,
                    "전체 설명은 /help",
                ]
            )
        )
        return

    try:
        source_language, target_language, source_text = _parse_translate_command_input(raw_text)
    except ValueError:
        await update.message.reply_text(
            "\n".join(
                [
                    "번역 형식이 맞지 않는다.",
                    "형식:",
                    "/translate <원문언어> | <목표언어> | <원문>",
                    "예시:",
                    "/translate jp | en | 締切は明日の18時です。",
                    LANGUAGE_HELP_TEXT,
                    "전체 설명은 /help",
                ]
            )
        )
        return

    await update.message.reply_text("번역 중이다. 잠깐 기다려라.")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    result = await asyncio.to_thread(
        service.translate_text,
        text=source_text,
        source_language=source_language,
        target_language=target_language,
    )
    await update.message.reply_text(f"번역 결과:\n{result['translated_text']}")


async def image_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """image_command

    Args:
        update: 텔레그램 업데이트 객체.
        context: 텔레그램 핸들러 컨텍스트.

    Returns:
        None: 프롬프트로 이미지를 생성해 결과를 전송한다.
    """
    await _ensure_user(update, context)
    LOGGER.info("image_command chat_id=%s raw_text=%s", update.effective_chat.id, update.message.text)
    service: DeadlineCoachService = context.application.bot_data["service"]
    raw_text = " ".join(context.args).strip()
    if not raw_text:
        await update.message.reply_text(
            "\n".join(
                [
                    "이미지 프롬프트가 비어 있다.",
                    "예시:",
                    "/image deadline enforcer poster, black and orange warning stripes",
                    "전체 설명은 /help",
                ]
            )
        )
        return

    await update.message.reply_text("이미지 생성 중이다. 길면 수십 초 걸린다. 기다려라.")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_PHOTO)
    result = await asyncio.to_thread(service.generate_image, prompt=raw_text)
    if result.get("error"):
        await update.message.reply_text(result.get("message", "이미지 생성에 실패했다."))
        return

    file_path = result.get("file_path")
    if not file_path:
        await update.message.reply_text("이미지를 만들었지만 파일 경로를 찾지 못했다. 다시 시도해라.")
        return

    with Path(file_path).open("rb") as image_file:
        try:
            await update.message.reply_photo(
                photo=image_file,
                caption="\n".join(
                    [
                        "이미지 생성 완료.",
                    ]
                ),
                read_timeout=TELEGRAM_READ_TIMEOUT_SECONDS,
                write_timeout=TELEGRAM_WRITE_TIMEOUT_SECONDS,
                connect_timeout=TELEGRAM_CONNECT_TIMEOUT_SECONDS,
                pool_timeout=TELEGRAM_POOL_TIMEOUT_SECONDS,
            )
        except TimedOut:
            LOGGER.warning("send_photo_timeout file_path=%s", file_path)
            await update.message.reply_text("이미지 생성은 끝났는데 텔레그램 업로드가 시간 초과로 실패했다. 다시 시도해라.")


async def file_assist_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """file_assist_command

    Args:
        update: 텔레그램 업데이트 객체.
        context: 텔레그램 핸들러 컨텍스트.

    Returns:
        None: 업로드된 파일 앞부분 최대 1500자 번역 결과를 전송한다.
    """
    await _ensure_user(update, context)
    raw_text = update.message.text.removeprefix("/file_assist").strip()
    LOGGER.info("file_assist_command chat_id=%s raw_text=%s", update.effective_chat.id, update.message.text)
    if not raw_text:
        await update.message.reply_text(
            "\n".join(
                [
                    "형식:",
                    "/file_assist <파일ID> | <원문언어> | <목표언어>",
                    "예: /file_assist 3 | jp | ko",
                    LANGUAGE_HELP_TEXT,
                ]
            )
        )
        return

    try:
        file_id, source_language, target_language = _parse_file_assist_input(raw_text)
    except ValueError:
        await update.message.reply_text(
            "\n".join(
                [
                    "형식이 맞지 않는다.",
                    "/file_assist <파일ID> | <원문언어> | <목표언어>",
                    "예: /file_assist 3 | jp | ko",
                    LANGUAGE_HELP_TEXT,
                ]
            )
        )
        return

    service: DeadlineCoachService = context.application.bot_data["service"]
    await update.message.reply_text("파일 앞부분 최대 1500자를 번역 중이다. 잠깐 기다려라.")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    try:
        result = await asyncio.to_thread(
            service.assist_file_translation,
            file_id,
            source_language,
            target_language,
        )
    except ValueError:
        await update.message.reply_text("파일을 찾지 못했다. /status 나 API에서 파일 ID를 다시 확인해라.")
        return

    output_dir = Path("data/file_assists")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"file_assist_{file_id}_{uuid4().hex[:8]}.txt"
    output_text = result["translated_text"].strip()
    output_path.write_text(output_text, encoding="utf-8")
    with output_path.open("rb") as output_file:
        await update.message.reply_document(
            document=output_file,
            filename=f"{Path(result['file_name']).stem}_translated.txt",
            caption="파일 번역 결과. 현재는 앞부분 최대 1500자만 포함한다.",
            read_timeout=TELEGRAM_READ_TIMEOUT_SECONDS,
            write_timeout=TELEGRAM_WRITE_TIMEOUT_SECONDS,
            connect_timeout=TELEGRAM_CONNECT_TIMEOUT_SECONDS,
            pool_timeout=TELEGRAM_POOL_TIMEOUT_SECONDS,
        )


async def _start_session(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    duration_minutes: int,
    mode: str,
) -> None:
    """_start_session

    Args:
        update: 텔레그램 업데이트 객체.
        context: 텔레그램 핸들러 컨텍스트.
        duration_minutes: 시작할 세션 길이.
        mode: 세션에 저장할 문자열 모드.

    Returns:
        None: 세션 생성 결과를 전송한다.
    """
    user = await _ensure_user(update, context)
    LOGGER.info(
        "start_session user_id=%s duration=%s mode=%s",
        user["id"],
        duration_minutes,
        mode,
    )
    service: DeadlineCoachService = context.application.bot_data["service"]
    projects = service.list_projects(user["id"])
    project_id = next((item["id"] for item in projects if item["status"] == "active"), None)
    session = service.start_session(user["id"], project_id, duration_minutes, mode)
    context.user_data["last_session_id"] = session["id"]

    # JobQueue가 활성화된 경우에만 후속 알림을 예약한다.
    if context.job_queue is not None:
        for elapsed_minutes in range(10, duration_minutes, 10):
            context.job_queue.run_once(
                send_session_progress_reminder,
                when=elapsed_minutes * 60,
                chat_id=update.effective_chat.id,
                data={
                    "session_id": session["id"],
                    "elapsed_minutes": elapsed_minutes,
                    "remaining_minutes": duration_minutes - elapsed_minutes,
                },
                name=f"session-progress-{session['id']}-{elapsed_minutes}",
            )
        context.job_queue.run_once(
            send_session_followup,
            when=duration_minutes * 60,
            chat_id=update.effective_chat.id,
            data={"session_id": session["id"]},
            name=f"session-{session['id']}",
        )

    lines = [
        f"{duration_minutes}분 세션 시작.",
        f"세션 ID: {session['id']}",
        "세션이 10분 이상이면 중간에 압박 메시지가 온다.",
        f"{duration_minutes}분이 끝나면 /report <작업량> 으로 숫자 보고",
    ]
    if context.job_queue is None:
        lines.append("참고: 현재 JobQueue가 없어 자동 종료 알림은 보내지 않는다.")

    await update.message.reply_text("\n".join(lines))


async def timer_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """timer_command

    Args:
        update: 텔레그램 업데이트 객체.
        context: 텔레그램 핸들러 컨텍스트.

    Returns:
        None: 사용자가 지정한 분 수로 세션을 시작한다.
    """
    await _ensure_user(update, context)
    LOGGER.info("timer_command chat_id=%s raw_text=%s", update.effective_chat.id, update.message.text)
    if not context.args:
        await update.message.reply_text(
            "\n".join(
                [
                    "시작할 분 수를 같이 보내면 된다.",
                    "예: /timer 25",
                    "10분 이상이면 중간 압박 메시지가 간다.",
                    "끝나면 /report <작업량> 으로 보고한다.",
                    "더 자세한 설명은 /help",
                ]
            )
        )
        return

    try:
        duration_minutes = int(context.args[0])
    except ValueError:
        await update.message.reply_text("분 수는 숫자로 넣어라. 예: /timer 25")
        return

    if duration_minutes < 1 or duration_minutes > 180:
        await update.message.reply_text("타이머는 1분 이상 180분 이하로 설정해라.")
        return

    await _start_session(update, context, duration_minutes, "timer")


async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """report_command

    Args:
        update: 텔레그램 업데이트 객체.
        context: 텔레그램 핸들러 컨텍스트.

    Returns:
        None: 마지막 세션 완료 보고를 반영하고 후속 지시를 전송한다.
    """
    user = await _ensure_user(update, context)
    LOGGER.info("report_command user_id=%s args=%s", user["id"], context.args)
    service: DeadlineCoachService = context.application.bot_data["service"]
    last_session_id = context.user_data.get("last_session_id")
    if not last_session_id:
        await update.message.reply_text(
            "\n".join(
                [
                    "아직 시작한 세션이 없다.",
                    "먼저 /timer <분>으로 세션부터 시작해라.",
                    "예: /timer 25",
                ]
            )
        )
        return

    existing_session = service.get_session(last_session_id)
    if not existing_session:
        context.user_data.pop("last_session_id", None)
        await update.message.reply_text("세션을 찾지 못했다. 다시 /timer 로 새 세션부터 시작해라.")
        return
    if existing_session["status"] != "active":
        context.user_data.pop("last_session_id", None)
        if existing_session.get("reported_result") == "AUTO_REPORT_0":
            await update.message.reply_text(
                "이전 세션은 미보고로 0 처리되어 이미 닫혔다. 이제 /timer <분> 으로 새 세션을 시작해라."
            )
        else:
            await update.message.reply_text("이전 세션은 이미 끝났다. /timer <분> 으로 새 세션을 시작해라.")
        return

    if not context.args:
        await update.message.reply_text(
            "\n".join(
                [
                    "완료량 숫자가 빠졌다.",
                    "예: /report 8",
                    "숫자는 이번 세션에서 실제로 끝낸 단위 수만 넣어라.",
                    "예를 들어 이번 25분 동안 8문장을 끝냈으면 /report 8 이다.",
                ]
            )
        )
        return

    try:
        completed_units = int(context.args[0])
    except ValueError:
        await update.message.reply_text("/report 뒤에는 숫자만 넣어라. 예: /report 8")
        return

    session = service.complete_session(
        session_id=last_session_id,
        result_text=update.message.text,
        completed_units_delta=completed_units,
    )
    if not session:
        await update.message.reply_text("세션을 찾지 못했다. 다시 /timer로 새 세션부터 시작해라.")
        return

    reply, timer_minutes, _, _ = service.chat(user["id"], f"{completed_units} 단위 완료 보고")
    await update.message.reply_text(
        "\n".join(
            [
                f"보고 반영 완료. 이번 세션은 {session['duration_minutes']}분.",
                f"이번에 반영된 작업량: {completed_units}",
                f"다음 권장 타이머: {timer_minutes}분",
                "",
                _sanitize_coach_text(reply),
            ]
        )
    )


async def send_session_followup(context: ContextTypes.DEFAULT_TYPE) -> None:
    """send_session_followup

    Args:
        context: 텔레그램 핸들러 컨텍스트.

    Returns:
        None: 세션 종료 후 보고 요청 메시지를 전송한다.
    """
    session_id = context.job.data["session_id"]
    LOGGER.info("send_session_followup session_id=%s chat_id=%s", session_id, context.job.chat_id)
    service: DeadlineCoachService = context.application.bot_data["service"]
    session = service.get_session(session_id)
    if not session or session["status"] == "completed":
        return

    user_id = session["user_id"]
    completed_session = service.complete_session(
        session_id=session_id,
        result_text="AUTO_REPORT_0",
        completed_units_delta=0,
    )
    reply = await asyncio.to_thread(
        service.coach_nudge,
        user_id,
        (
            "타이머가 끝났는데 사용자가 아직 보고하지 않았다. "
            "이번 세션은 방금 작업량 0으로 자동 마감 처리됐다. "
            "이제 사용자는 보고를 다시 할 필요가 없다. "
            "지금 바로 새 /timer <분> 을 시작하게 만드는 짧고 강한 압박 메시지를 보내라."
        ),
        session.get("project_id"),
    )
    await context.bot.send_message(chat_id=context.job.chat_id, text=_sanitize_coach_text(reply))


async def send_session_progress_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    """send_session_progress_reminder

    Args:
        context: 텔레그램 핸들러 컨텍스트.

    Returns:
        None: 10분 단위 중간 진행 알림을 전송한다.
    """
    session_id = context.job.data["session_id"]
    elapsed_minutes = context.job.data["elapsed_minutes"]
    remaining_minutes = context.job.data["remaining_minutes"]
    LOGGER.info(
        "send_session_progress_reminder session_id=%s chat_id=%s elapsed=%s remaining=%s",
        session_id,
        context.job.chat_id,
        elapsed_minutes,
        remaining_minutes,
    )
    service: DeadlineCoachService = context.application.bot_data["service"]
    session = service.get_session(session_id)
    if not session or session["status"] == "completed":
        return
    user_id = session["user_id"]
    reply = await asyncio.to_thread(
        service.coach_nudge,
        user_id,
        (
            f"타이머 세션 진행 중이다. {elapsed_minutes}분 지났고 {remaining_minutes}분 남았다. "
            "사용자가 계속 번역하게 만드는 짧은 압박 메시지를 보내라. 지금은 /report가 아니라 계속 작업하라고 해라."
        ),
        session.get("project_id"),
    )
    await context.bot.send_message(chat_id=context.job.chat_id, text=_sanitize_coach_text(reply))


async def send_daily_checkin(context: ContextTypes.DEFAULT_TYPE) -> None:
    """send_daily_checkin

    Args:
        context: 텔레그램 핸들러 컨텍스트.

    Returns:
        None: 특정 시간대 자동 체크인 리마인더를 발송한다.
    """
    service: DeadlineCoachService = context.application.bot_data["service"]
    now_utc = datetime.now(UTC)
    for user in service.list_users():
        try:
            timezone = ZoneInfo(user["timezone"])
        except Exception:  # noqa: BLE001
            timezone = ZoneInfo("Asia/Seoul")
        local_now = now_utc.astimezone(timezone)
        if local_now.hour not in CHECKIN_HOURS:
            continue

        reminder_key = f"checkin-{local_now.hour}"
        reminder_date = local_now.date().isoformat()
        if service.database.has_reminder_log(user["id"], reminder_key, reminder_date):
            continue

        project = service.get_active_project(user["id"])
        if not project:
            continue

        daily_report = service.build_daily_report(user["id"])
        if daily_report["focus_minutes"] > 0 and local_now.hour == CHECKIN_HOURS[0]:
            service.database.add_reminder_log(user["id"], reminder_key, reminder_date)
            continue

        platform_user_id = user["platform_user_id"]
        if not str(platform_user_id).startswith("telegram-"):
            continue
        chat_id = int(str(platform_user_id).removeprefix("telegram-"))
        reply = await asyncio.to_thread(
            service.coach_nudge,
            user["id"],
            (
                f"지금은 자동 체크인 시간대다. 현재 시간은 {local_now.strftime('%H:%M')}이고 "
                f"오늘 집중 시간은 {daily_report['focus_minutes']}분이다. "
                "활성 프로젝트 기준으로 지금 바로 /timer 를 시작하게 만드는 짧고 강한 메시지를 보내라."
            ),
            project["id"],
        )
        await context.bot.send_message(chat_id=chat_id, text=_sanitize_coach_text(reply))
        service.database.add_reminder_log(user["id"], reminder_key, reminder_date)


async def document_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """document_message

    Args:
        update: 텔레그램 업데이트 객체.
        context: 텔레그램 핸들러 컨텍스트.

    Returns:
        None: 텍스트 파일을 활성 프로젝트 파일로 등록한다.
    """
    user = await _ensure_user(update, context)
    service: DeadlineCoachService = context.application.bot_data["service"]
    projects = service.list_projects(user["id"])
    project = next((item for item in projects if item["status"] == "active"), None)
    if not project:
        await update.message.reply_text("활성 프로젝트가 없다. 먼저 프로젝트부터 등록해라.")
        return

    document = update.message.document
    LOGGER.info("document_message user_id=%s file_name=%s mime=%s", user["id"], document.file_name, document.mime_type)
    if document.file_size and document.file_size > 2_000_000:
        await update.message.reply_text("지금은 2MB 이하 텍스트 파일만 받는다.")
        return
    if document.mime_type and not document.mime_type.startswith("text/") and not (document.file_name or "").endswith(".txt"):
        await update.message.reply_text("지금은 .txt 같은 텍스트 파일만 받는다.")
        return

    await update.message.reply_text("파일을 읽는 중이다. 잠깐 기다려라.")
    telegram_file = await document.get_file()
    payload = await telegram_file.download_as_bytearray()
    text = bytes(payload).decode("utf-8", errors="ignore").strip()
    if not text:
        await update.message.reply_text("파일 내용이 비어 있다.")
        return

    created = await asyncio.to_thread(
        service.create_project_file,
        {
            "project_id": project["id"],
            "name": document.file_name or f"file-{document.file_id}.txt",
            "source_text": text,
        },
    )
    overview = service.build_project_overview(project["id"])
    await update.message.reply_text(
        "\n".join(
            [
                f"파일 등록 완료: {created['name']}",
                f"파일 ID: {created['id']}",
                f"자동 집계: {created['source_segments']} 세그먼트, {created['source_chars']}자",
                f"현재 프로젝트 파일: 남은 {overview['remaining_file_count']}개 / 전체 {overview['file_count']}개",
                f"보조 번역 예시: /file_assist {created['id']} | {project['source_language']} | {project['target_language']}",
                "파일 번역 보조는 현재 앞부분 최대 1500자까지 처리한다.",
            ]
        )
    )


async def text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """text_message

    Args:
        update: 텔레그램 업데이트 객체.
        context: 텔레그램 핸들러 컨텍스트.

    Returns:
        None: 일반 텍스트 메시지를 코칭 서비스로 넘긴다.
    """
    user = await _ensure_user(update, context)
    LOGGER.info("text_message user_id=%s text=%s", user["id"], update.message.text)
    if update.message.text == PROJECT_TEMPLATE_LABEL:
        await project_template_message(update, context)
        return
    if update.message.text == PROJECT_UPDATE_LABEL:
        await project_update_template_message(update, context)
        return
    if update.message.text == PROJECT_DELETE_LABEL:
        await project_delete_template_message(update, context)
        return
    if update.message.text == PROJECT_LIST_LABEL:
        await deadline_list_command(update, context)
        return
    if update.message.text == PROJECT_SWITCH_LABEL:
        await project_switch_template_message(update, context)
        return
    if update.message.text == STATUS_LABEL:
        await status_command(update, context)
        return
    if update.message.text == HELP_LABEL:
        await help_command(update, context)
        return
    if update.message.text == TIMER_TEMPLATE_LABEL:
        await timer_template_message(update, context)
        return
    if update.message.text == REPORT_LABEL:
        await report_template_message(update, context)
        return
    if update.message.text == TRANSLATE_TEMPLATE_LABEL:
        await translate_template_message(update, context)
        return
    if update.message.text == IMAGE_TEMPLATE_LABEL:
        await image_template_message(update, context)
        return
    if update.message.text == FILE_ASSIST_TEMPLATE_LABEL:
        await file_assist_template_message(update, context)
        return
    if _looks_like_project_input(update.message.text):
        if await _create_project_from_text(update, context, update.message.text, user):
            return
    likely_translation_request = _looks_like_translation_request(update.message.text)
    likely_image_request = _looks_like_image_request(update.message.text)
    service: DeadlineCoachService = context.application.bot_data["service"]
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    reply, _, executed_tools, tool_results = await asyncio.to_thread(service.chat, user["id"], update.message.text)
    translation_result = tool_results.get("translate_text") if "translate_text" in executed_tools else None
    if translation_result and translation_result.get("translated_text"):
        await update.message.reply_text(f"번역 결과:\n{translation_result['translated_text']}")
        return
    if likely_translation_request:
        await update.message.reply_text(
            "번역 요청으로 이해했지만 모델이 번역 도구를 제대로 호출하지 못했다. 한 번 더 보내거나 /translate <원문언어> | <목표언어> | <원문> 형식을 써라."
        )
        return
    image_result = tool_results.get("generate_image") if "generate_image" in executed_tools else None
    if image_result and image_result.get("file_path") and not image_result.get("error"):
        file_path = image_result["file_path"]
        with Path(file_path).open("rb") as image_file:
            try:
                await update.message.reply_photo(
                    photo=image_file,
                    caption="이미지 생성 완료.",
                    read_timeout=TELEGRAM_READ_TIMEOUT_SECONDS,
                    write_timeout=TELEGRAM_WRITE_TIMEOUT_SECONDS,
                    connect_timeout=TELEGRAM_CONNECT_TIMEOUT_SECONDS,
                    pool_timeout=TELEGRAM_POOL_TIMEOUT_SECONDS,
                )
            except TimedOut:
                LOGGER.warning("send_photo_timeout file_path=%s", file_path)
                await update.message.reply_text("이미지 생성은 끝났는데 텔레그램 업로드가 시간 초과로 실패했다. 다시 시도해라.")
        return
    if "generate_image" in executed_tools:
        return
    if likely_image_request:
        await update.message.reply_text("이미지 요청으로 이해했지만 모델이 이미지 도구를 제대로 호출하지 못했다. 한 번 더 보내거나 /image 명령을 써라.")
        return
    sanitized_reply = "\n".join(
        line for line in reply.splitlines() if "파일 경로:" not in line and "data/generated_images/" not in line
    ).strip()
    await update.message.reply_text(_sanitize_coach_text(sanitized_reply or "지금 상태를 한 번만 더 짧게 보내라."))


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """error_handler

    Args:
        update: 실패를 일으킨 업데이트 객체 또는 기타 이벤트.
        context: 텔레그램 핸들러 컨텍스트.

    Returns:
        None: 예외를 로그로 남기고 가능하면 사용자에게 오류를 안내한다.
    """
    LOGGER.exception("telegram_handler_error update=%s", update, exc_info=context.error)
    if isinstance(update, Update) and update.effective_message is not None:
        await update.effective_message.reply_text("처리 중 오류가 났다. 같은 요청을 한 번만 더 보내라.")


def build_application() -> Application:
    """build_application

    Args:
        없음.

    Returns:
        Application: 핸들러와 공용 서비스를 주입한 텔레그램 애플리케이션.
    """
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise ValueError("DFY_TELEGRAM_BOT_TOKEN 이 필요하다.")

    application = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .connect_timeout(TELEGRAM_CONNECT_TIMEOUT_SECONDS)
        .read_timeout(TELEGRAM_READ_TIMEOUT_SECONDS)
        .write_timeout(TELEGRAM_WRITE_TIMEOUT_SECONDS)
        .pool_timeout(TELEGRAM_POOL_TIMEOUT_SECONDS)
        .build()
    )
    application.bot_data["service"] = build_service()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("deadline_add", deadline_add_command))
    application.add_handler(CommandHandler("deadline_update", deadline_update_command))
    application.add_handler(CommandHandler("deadline_delete", deadline_delete_command))
    application.add_handler(CommandHandler("deadline_list", deadline_list_command))
    application.add_handler(CommandHandler("deadline_switch", deadline_switch_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("timer", timer_command))
    application.add_handler(CommandHandler("translate", translate_command))
    application.add_handler(CommandHandler("image", image_command))
    application.add_handler(CommandHandler("file_assist", file_assist_command))
    application.add_handler(CommandHandler("report", report_command))
    application.add_handler(MessageHandler(filters.Document.ALL, document_message))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message))
    application.add_error_handler(error_handler)
    if application.job_queue is not None:
        application.job_queue.run_repeating(send_daily_checkin, interval=1800, first=60, name="daily-checkin")
    return application


def main() -> None:
    """main

    Args:
        없음.

    Returns:
        None: 텔레그램 봇 polling 루프를 시작한다.
    """
    LOGGER.info("telegram_bot_starting")
    application = build_application()
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
