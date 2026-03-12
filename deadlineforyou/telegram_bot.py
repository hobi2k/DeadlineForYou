from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from deadlineforyou.config import get_settings
from deadlineforyou.domain import CoachingMode
from deadlineforyou.providers import build_provider
from deadlineforyou.service import DeadlineCoachService
from deadlineforyou.storage import Database


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
    await update.message.reply_text(
        "\n".join(
            [
                "마감 집행관 「締切監督」 투입.",
                f"등록된 사용자: {user['nickname']}",
                "지금 할 수 있는 것:",
                "/deadline_add - 프로젝트 등록",
                "/deadline_list - 프로젝트 목록 확인",
                "/status - 현재 프로젝트와 진행률 확인",
                "/start10 - 10분 강제 시동 세션",
                "/start15 - 15분 구조 복구 세션",
                "/pomodoro - 25분 포모도로 세션",
                "/report 8 - 방금 끝낸 작업량 보고",
                "평문으로 메시지를 보내도 바로 압박을 시작한다.",
            ]
        )
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
    await update.message.reply_text(
        "\n".join(
            [
                "/start - 사용자 등록과 시작 안내",
                "/deadline_add <제목> | <총량> | <YYYY-MM-DD HH:MM> | <단위>",
                "예: /deadline_add 게임 시나리오 번역 | 120 | 2026-03-14 18:00 | 문장",
                "/deadline_list - 프로젝트 목록 확인",
                "/status - 현재 활성 프로젝트 상태",
                "/start10 - 10분 세션 시작",
                "/start15 - 15분 세션 시작",
                "/pomodoro - 25분 세션 시작",
                "/report <숫자> - 방금 끝낸 작업량 반영",
                "예: /report 12",
                "평문 메시지 예: 하기 싫다 / 마감 4시간 전인데 절반 남음",
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
    service: DeadlineCoachService = context.application.bot_data["service"]
    projects = service.list_projects(user["id"])
    if not projects:
        await update.message.reply_text(
            "아직 등록된 프로젝트가 없다.\nREST API나 Swagger UI에서 먼저 프로젝트를 만들어라."
        )
        return

    project = next((item for item in projects if item["status"] == "active"), projects[0])
    report = service.build_daily_report(user["id"])
    await update.message.reply_text(
        "\n".join(
            [
                f"프로젝트: {project['title']}",
                f"진행률: {project['completed_units']}/{project['total_units']} {project['unit_label']}",
                f"마감: {project['deadline_at']}",
                f"오늘 집중: {report['focus_minutes']}분",
                f"오늘 회피: {report['avoidance_count']}회",
            ]
        )
    )


def _parse_deadline_input(raw_text: str, timezone_name: str) -> tuple[str, int, datetime, str]:
    """_parse_deadline_input

    Args:
        raw_text: `/deadline_add` 뒤에 입력된 원문.
        timezone_name: 사용자 시간대 이름.

    Returns:
        tuple[str, int, datetime, str]: 제목, 총량, 마감 시각, 단위명.
    """
    parts = [part.strip() for part in raw_text.split("|")]
    if len(parts) < 3:
        raise ValueError("입력 형식이 부족하다.")

    title = parts[0]
    total_units = int(parts[1])
    deadline_str = parts[2]
    unit_label = parts[3] if len(parts) >= 4 and parts[3] else "문장"

    # 시간대가 없는 입력은 사용자의 기본 시간대로 해석한다.
    deadline_at = datetime.fromisoformat(deadline_str.replace(" ", "T"))
    if deadline_at.tzinfo is None:
        deadline_at = deadline_at.replace(tzinfo=ZoneInfo(timezone_name))
    return title, total_units, deadline_at, unit_label


async def deadline_add_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """deadline_add_command

    Args:
        update: 텔레그램 업데이트 객체.
        context: 텔레그램 핸들러 컨텍스트.

    Returns:
        None: 새 프로젝트를 등록하고 활성 프로젝트로 안내한다.
    """
    user = await _ensure_user(update, context)
    service: DeadlineCoachService = context.application.bot_data["service"]

    raw_text = update.message.text.removeprefix("/deadline_add").strip()
    if not raw_text:
        await update.message.reply_text(
            "\n".join(
                [
                    "형식부터 맞춰라.",
                    "/deadline_add <제목> | <총량> | <YYYY-MM-DD HH:MM> | <단위>",
                    "예: /deadline_add 게임 시나리오 번역 | 120 | 2026-03-14 18:00 | 문장",
                ]
            )
        )
        return

    try:
        title, total_units, deadline_at, unit_label = _parse_deadline_input(raw_text, user["timezone"])
    except ValueError:
        await update.message.reply_text(
            "입력 형식이 틀렸다.\n예: /deadline_add 게임 시나리오 번역 | 120 | 2026-03-14 18:00 | 문장"
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
            "source_language": "ja",
            "target_language": "ko",
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
                f"분량: {project['completed_units']}/{project['total_units']} {project['unit_label']}",
                f"마감: {project['deadline_at']}",
                "이제 /status로 확인하고 바로 /start10 쳐라.",
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
    service: DeadlineCoachService = context.application.bot_data["service"]
    projects = service.list_projects(user["id"])
    if not projects:
        await update.message.reply_text("등록된 프로젝트가 없다. /deadline_add부터 쳐라.")
        return

    lines = ["현재 프로젝트 목록:"]
    for project in projects[:10]:
        lines.append(
            f"- [{project['status']}] {project['title']} | "
            f"{project['completed_units']}/{project['total_units']} {project['unit_label']} | "
            f"{project['deadline_at']}"
        )
    await update.message.reply_text("\n".join(lines))


async def _start_session(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    duration_minutes: int,
    mode: CoachingMode,
) -> None:
    """_start_session

    Args:
        update: 텔레그램 업데이트 객체.
        context: 텔레그램 핸들러 컨텍스트.
        duration_minutes: 시작할 세션 길이.
        mode: 세션에 붙일 코칭 모드.

    Returns:
        None: 세션 생성 결과를 전송한다.
    """
    user = await _ensure_user(update, context)
    service: DeadlineCoachService = context.application.bot_data["service"]
    projects = service.list_projects(user["id"])
    project_id = next((item["id"] for item in projects if item["status"] == "active"), None)
    session = service.start_session(user["id"], project_id, duration_minutes, mode)
    context.user_data["last_session_id"] = session["id"]

    # JobQueue가 활성화된 경우에만 후속 알림을 예약한다.
    if context.job_queue is not None:
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
        "지금 할 일:",
        "파일 열기",
        "첫 문장부터 번역",
        f"{duration_minutes}분 끝나면 /report <작업량> 으로 보고",
    ]
    if context.job_queue is None:
        lines.append("참고: 현재 JobQueue가 없어 자동 종료 알림은 보내지 않는다.")

    await update.message.reply_text("\n".join(lines))


async def start10_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """start10_command

    Args:
        update: 텔레그램 업데이트 객체.
        context: 텔레그램 핸들러 컨텍스트.

    Returns:
        None: 10분 세션을 시작한다.
    """
    await _start_session(update, context, 10, CoachingMode.force_start)


async def start15_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """start15_command

    Args:
        update: 텔레그램 업데이트 객체.
        context: 텔레그램 핸들러 컨텍스트.

    Returns:
        None: 15분 세션을 시작한다.
    """
    await _start_session(update, context, 15, CoachingMode.cold_support)


async def pomodoro_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """pomodoro_command

    Args:
        update: 텔레그램 업데이트 객체.
        context: 텔레그램 핸들러 컨텍스트.

    Returns:
        None: 25분 포모도로 세션을 시작한다.
    """
    await _start_session(update, context, 25, CoachingMode.boss_mode)


async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """report_command

    Args:
        update: 텔레그램 업데이트 객체.
        context: 텔레그램 핸들러 컨텍스트.

    Returns:
        None: 마지막 세션 완료 보고를 반영하고 후속 지시를 전송한다.
    """
    user = await _ensure_user(update, context)
    service: DeadlineCoachService = context.application.bot_data["service"]
    last_session_id = context.user_data.get("last_session_id")
    if not last_session_id:
        await update.message.reply_text("먼저 /start10, /start15, /pomodoro 중 하나로 세션부터 시작해라.")
        return

    if context.args:
        try:
            completed_units = int(context.args[0])
        except ValueError:
            await update.message.reply_text("/report 뒤에는 숫자만 넣어라. 예: /report 8")
            return
    else:
        completed_units = 0

    session = service.complete_session(
        session_id=last_session_id,
        result_text=update.message.text,
        completed_units_delta=completed_units,
    )
    if not session:
        await update.message.reply_text("세션을 찾지 못했다. 다시 /start10부터 시작해라.")
        return

    reply, evaluation, _ = service.chat(user["id"], f"{completed_units} {('단위 완료' if completed_units else '세션 완료')}")
    await update.message.reply_text(
        "\n".join(
            [
                f"보고 반영 완료. 이번 세션은 {session['duration_minutes']}분.",
                f"추가 반영 작업량: {completed_units}",
                f"다음 권장 타이머: {evaluation.timer_minutes}분",
                "",
                reply,
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
    await context.bot.send_message(
        chat_id=context.job.chat_id,
        text=(
            f"세션 {session_id} 종료 시각이다.\n"
            "번역량 숫자와 함께 /report <작업량> 으로 보고해.\n"
            "또 도망쳤으면 그것도 바로 들킨다."
        ),
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
    service: DeadlineCoachService = context.application.bot_data["service"]
    reply, _, _ = service.chat(user["id"], update.message.text)
    await update.message.reply_text(reply)


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

    application = Application.builder().token(settings.telegram_bot_token).build()
    application.bot_data["service"] = build_service()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("deadline_add", deadline_add_command))
    application.add_handler(CommandHandler("deadline_list", deadline_list_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("start10", start10_command))
    application.add_handler(CommandHandler("start15", start15_command))
    application.add_handler(CommandHandler("pomodoro", pomodoro_command))
    application.add_handler(CommandHandler("report", report_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message))
    return application


def main() -> None:
    """main

    Args:
        없음.

    Returns:
        None: 텔레그램 봇 polling 루프를 시작한다.
    """
    application = build_application()
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
