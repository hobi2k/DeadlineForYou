from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
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
TIMER_TEMPLATE_LABEL = "타이머 시작 양식"
TRANSLATE_TEMPLATE_LABEL = "번역 양식"
IMAGE_TEMPLATE_LABEL = "이미지 양식"

SUPPORTED_LANGUAGE_CODES = {"ko", "jp", "en", "ch"}
LANGUAGE_HELP_TEXT = "지원 언어 코드는 ko, jp, en, ch만 쓴다."


TELEGRAM_READ_TIMEOUT_SECONDS = 120
TELEGRAM_WRITE_TIMEOUT_SECONDS = 120
TELEGRAM_CONNECT_TIMEOUT_SECONDS = 30
TELEGRAM_POOL_TIMEOUT_SECONDS = 30


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
            [PROJECT_TEMPLATE_LABEL, "/deadline_list"],
            ["/status", "/help"],
            [TIMER_TEMPLATE_LABEL, "/report"],
            [TRANSLATE_TEMPLATE_LABEL, IMAGE_TEMPLATE_LABEL],
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
                "처음 쓰는 사람 기준 사용 순서:",
                "1. 프로젝트 등록 양식 버튼을 눌러 등록 예시를 본다.",
                "2. 예시 줄에서 제목, 언어, 총량, 마감 시간만 바꿔서 보낸다.",
                "3. /status 로 지금 활성 프로젝트가 맞는지 확인한다.",
                "4. 타이머 시작 양식 버튼을 눌러 /timer 예시를 본다.",
                "5. /timer 25 같이 보내서 작업 세션을 시작한다.",
                "6. 세션이 끝나면 /report 12 같이 숫자로 완료량을 보고한다.",
                "",
                "프로젝트 등록에서 시간은 작업 시간 아니라 마감 시각이다.",
                "예: 2026-03-14 18:00 = 이 프로젝트의 최종 마감 시간",
                "",
                "짧은 번역은 /translate",
                "이미지 생성은 /image",
                LANGUAGE_HELP_TEXT,
                "",
                "예시 버튼은 형식을 알려준다.",
                "예시 줄은 /deadline_add 없이 그대로 보내도 프로젝트 등록으로 처리한다.",
                "더 자세한 설명과 예시는 /help",
                "평문 메시지도 바로 코칭한다.",
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
                "사용 방법 요약:",
                "1. 프로젝트를 등록한다.",
                "2. /status 로 현재 프로젝트를 확인한다.",
                "3. /timer <분> 으로 작업을 시작한다.",
                "4. 세션이 끝나면 /report <작업량> 으로 숫자 보고를 한다.",
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
                "단위는 문장, 페이지, 줄 같은 작업 단위명이다.",
                "예: /deadline_add 게임 시나리오 번역 | jp | ko | 120 | 2026-03-14 18:00 | 문장",
                "또는 명령 없이",
                "게임 시나리오 번역 | jp | ko | 120 | 2026-03-14 18:00 | 문장",
                LANGUAGE_HELP_TEXT,
                "",
                "/deadline_list",
                "프로젝트 목록 확인",
                "",
                "/status",
                "현재 활성 프로젝트와 오늘 진행 상황 확인",
                "지금 어떤 프로젝트가 활성인지, 오늘 몇 분 했는지 본다.",
                "",
                "/timer <분>",
                "원하는 분 수로 타이머 세션 시작",
                "예: /timer 10, /timer 25, /timer 45",
                "10분 이상이면 10분마다 압박 메시지가 온다.",
                "끝나면 /report <작업량> 으로 숫자 보고를 해야 한다.",
                "예: 이번 세션에서 8문장을 끝냈으면 /report 8",
                "",
                "/report <숫자>",
                "방금 끝낸 작업량 보고",
                "예: /report 12",
                "숫자가 없으면 반영되지 않는다.",
                "여기 숫자는 이번 세션에서 실제로 끝낸 양만 넣는다.",
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
                    "프로젝트 등록 양식 버튼을 누르거나 아래 형식으로 바로 보내라.",
                    "게임 시나리오 번역 | jp | ko | 120 | 2026-03-14 18:00 | 문장",
                ]
            )
        )
        return

    project = next((item for item in projects if item["status"] == "active"), projects[0])
    report = service.build_daily_report(user["id"])
    await update.message.reply_text(
        "\n".join(
            [
                f"프로젝트: {project['title']}",
                f"언어: {project['source_language']} -> {project['target_language']}",
                f"진행률: {project['completed_units']}/{project['total_units']} {project['unit_label']}",
                f"마감: {project['deadline_at']}",
                f"오늘 집중: {report['focus_minutes']}분",
                f"오늘 완료량: {report['completed_units']}",
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
    total_units = int(parts[3])
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
        lines.append(
            f"- [{project['status']}] {project['title']} | "
            f"{project['source_language']}->{project['target_language']} | "
            f"{project['completed_units']}/{project['total_units']} {project['unit_label']} | "
            f"{project['deadline_at']}"
        )
    await update.message.reply_text("\n".join(lines))


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
                "또는 /deadline_add 없이",
                "게임 시나리오 번역 | jp | ko | 120 | 2026-03-14 18:00 | 문장",
                "형식 뜻:",
                "제목 | 원문언어 | 목표언어 | 총량 | 마감시각 | 단위",
                "예: 게임 시나리오 번역 | jp | ko | 120 | 2026-03-14 18:00 | 문장",
                LANGUAGE_HELP_TEXT,
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
    if update.message.text == TIMER_TEMPLATE_LABEL:
        await timer_template_message(update, context)
        return
    if update.message.text == TRANSLATE_TEMPLATE_LABEL:
        await translate_template_message(update, context)
        return
    if update.message.text == IMAGE_TEMPLATE_LABEL:
        await image_template_message(update, context)
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
    application.add_handler(CommandHandler("deadline_list", deadline_list_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("timer", timer_command))
    application.add_handler(CommandHandler("translate", translate_command))
    application.add_handler(CommandHandler("image", image_command))
    application.add_handler(CommandHandler("report", report_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message))
    application.add_error_handler(error_handler)
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
