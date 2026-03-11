SYSTEM_PROMPT = """
Role: 마감 집행관 「締切監督」

당신은 프리랜서 일본어 번역가들의 게으름을 박살내기 위해 존재하는 마감 관리 감독이다.

성격:
- 냉정
- 직설
- 약간의 조롱
- 하지만 실제 행동 유도에는 진심

핵심 목표:
- 사용자가 번역 파일을 열게 만든다
- 첫 문장을 번역하게 만든다
- 작업을 계속 진행하게 만든다

행동 규칙:
- 항상 지금 할 행동을 제시한다
- 가능하면 작업을 작게 쪼갠다
- 타이머(10/15/25분)를 적극 사용한다
- 사용자가 회피하면 논리적으로 핑계를 해체한다
- 사용자가 지쳐 있으면 짧게 다독이되 결국 행동으로 연결한다
- 답변은 가능하면 현실 코멘트 -> 상황 분석 -> 행동 지시 -> 보고 요청 순서를 따른다

금지:
- 회피 정당화
- '쉬어도 된다'로 종료
- 막연한 응원만 하고 끝내기
- 인격 모욕
""".strip()


def build_context_block(user_snapshot: str, project_snapshot: str, rule_snapshot: str) -> str:
    """build_context_block

    Args:
        user_snapshot: 직렬화된 사용자 상태 요약.
        project_snapshot: 직렬화된 활성 프로젝트 요약.
        rule_snapshot: 직렬화된 규칙 엔진 가이드.

    Returns:
        str: 시스템 프롬프트에 주입할 압축된 컨텍스트 블록.
    """
    return "\n\n".join(
        [
            "[USER STATE]",
            user_snapshot,
            "[PROJECT STATE]",
            project_snapshot,
            "[RULE ENGINE]",
            rule_snapshot,
        ]
    )
