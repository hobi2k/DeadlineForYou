from __future__ import annotations

import json
import re
import uuid
from abc import ABC, abstractmethod
from typing import Any

from openai import OpenAI
from transformers import AutoModelForCausalLM
from transformers.models.qwen2.tokenization_qwen2 import Qwen2Tokenizer

from deadlineforyou.config import Settings
from deadlineforyou.domain import GenerationResult, ToolCall


class LLMProvider(ABC):
    @abstractmethod
    def generate_turn(
        self,
        system_prompt: str,
        context_block: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> GenerationResult:
        """generate_turn

        Args:
            system_prompt: 기본 페르소나와 행동 규칙.
            context_block: 실행 시점 상태가 담긴 컨텍스트 블록.
            messages: 현재 턴까지의 대화 메시지 목록.
            tools: 모델이 호출할 수 있는 도구 정의 목록.

        Returns:
            GenerationResult: 모델 응답 텍스트와 tool call 목록.
        """
        raise NotImplementedError

    def supports_tool_calling(self) -> bool:
        """supports_tool_calling

        Args:
            없음.

        Returns:
            bool: provider가 tool calling을 지원하면 True.
        """
        return False


class OpenAIProvider(LLMProvider):
    def __init__(self, settings: Settings) -> None:
        """__init__

        Args:
            settings: OpenAI 자격 정보와 모델명이 담긴 애플리케이션 설정.

        Returns:
            None: provider 클라이언트를 초기화한다.
        """
        if not settings.openai_api_key:
            raise ValueError("DFY_OPENAI_API_KEY is required when llm_provider=openai")
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.llm_model

    def generate_turn(
        self,
        system_prompt: str,
        context_block: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> GenerationResult:
        """generate_turn

        Args:
            system_prompt: 기본 페르소나와 행동 규칙.
            context_block: 실행 시점 상태가 담긴 컨텍스트 블록.
            messages: 현재 턴까지의 대화 메시지 목록.
            tools: 모델이 호출할 수 있는 도구 정의 목록.

        Returns:
            GenerationResult: OpenAI가 생성한 텍스트와 tool call 목록.
        """
        # 시스템 메시지에 규칙과 상태를 먼저 고정해 두어 대화 이력이 이를 덮어쓰지 못하게 한다.
        request_messages = [{"role": "system", "content": f"{system_prompt}\n\n{context_block}"}]
        request_messages.extend(messages)
        kwargs: dict[str, Any] = {"model": self.model, "messages": request_messages}
        if tools:
            kwargs["tools"] = tools
        response = self.client.chat.completions.create(**kwargs)
        message = response.choices[0].message
        tool_calls: list[ToolCall] = []
        if message.tool_calls:
            for tool_call in message.tool_calls:
                arguments = tool_call.function.arguments
                parsed = json.loads(arguments) if isinstance(arguments, str) and arguments else {}
                tool_calls.append(ToolCall(id=tool_call.id, name=tool_call.function.name, arguments=parsed))
        return GenerationResult(text=(message.content or "").strip(), tool_calls=tool_calls)

    def supports_tool_calling(self) -> bool:
        """supports_tool_calling

        Args:
            없음.

        Returns:
            bool: OpenAI provider는 native tool calling을 지원한다.
        """
        return True


class LocalOpenAICompatibleProvider(LLMProvider):
    def __init__(self, settings: Settings) -> None:
        """__init__

        Args:
            settings: 로컬 모델 로딩 옵션이 담긴 애플리케이션 설정.

        Returns:
            None: 토크나이저와 모델을 메모리에 적재한다.
        """
        model_path = settings.local_model_path
        if not model_path.exists():
            raise ValueError(f"Local model path does not exist: {model_path}")
        # Qwen3 계열 체크포인트는 현재 환경의 AutoTokenizer 경로에서
        # fast tokenizer 충돌이 날 수 있어 slow Qwen2Tokenizer를 직접 사용한다.
        self.tokenizer = Qwen2Tokenizer.from_pretrained(
            model_path,
            trust_remote_code=True,
        )
        self.model = AutoModelForCausalLM.from_pretrained(
            model_path,
            trust_remote_code=True,
            device_map=settings.local_device_map,
            dtype="auto",
        )
        self.max_new_tokens = settings.local_max_new_tokens
        self.temperature = settings.local_temperature

    def generate_turn(
        self,
        system_prompt: str,
        context_block: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> GenerationResult:
        """generate_turn

        Args:
            system_prompt: 기본 페르소나와 행동 규칙.
            context_block: 실행 시점 상태가 담긴 컨텍스트 블록.
            messages: 현재 턴까지의 대화 메시지 목록.
            tools: 모델이 호출할 수 있는 도구 정의 목록.

        Returns:
            GenerationResult: 로컬 모델이 생성한 텍스트와 tool call 목록.
        """
        rendered_messages = [{"role": "system", "content": f"{system_prompt}\n\n{context_block}"}]
        rendered_messages.extend(messages)
        # 모델이 기대하는 원래 채팅 포맷으로 렌더링해 Saya 말투와 응답 형식을 안정적으로 유지한다.
        prompt = self.tokenizer.apply_chat_template(
            rendered_messages,
            tools=tools,
            tokenize=False,
            add_generation_prompt=True,
        )
        model_inputs = self.tokenizer([prompt], return_tensors="pt").to(self.model.device)
        # 입력 프롬프트 구간을 제외한 새 생성 토큰만 잘라서 호출자에게 반환한다.
        generated_ids = self.model.generate(
            **model_inputs,
            max_new_tokens=self.max_new_tokens,
            do_sample=True,
            temperature=self.temperature,
            top_p=0.8,
            top_k=20,
        )
        completion_ids = generated_ids[:, model_inputs.input_ids.shape[1]:]
        output = self.tokenizer.batch_decode(completion_ids, skip_special_tokens=True)[0]
        tool_calls, text = _parse_local_tool_calls(output)
        return GenerationResult(text=text, tool_calls=tool_calls)

    def supports_tool_calling(self) -> bool:
        """supports_tool_calling

        Args:
            없음.

        Returns:
            bool: 로컬 Qwen3 provider는 텍스트 기반 tool calling을 지원한다.
        """
        return True


class ScriptedFallbackProvider(LLMProvider):
    def generate_turn(
        self,
        system_prompt: str,
        context_block: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> GenerationResult:
        """generate_turn

        Args:
            system_prompt: 기본 페르소나와 행동 규칙.
            context_block: 실행 시점 상태가 담긴 컨텍스트 블록.
            messages: 현재 턴까지의 대화 메시지 목록.
            tools: 모델이 호출할 수 있는 도구 정의 목록.

        Returns:
            GenerationResult: 모델 없이 로컬 테스트를 할 때 쓰는 고정 응답.
        """
        del system_prompt, tools
        last_user = next((item["content"] for item in reversed(messages) if item["role"] == "user"), "")
        return GenerationResult(
            text=(
                "그래서 지금 번역은 했어?\n"
                f"{last_user}\n"
                "지금 할 일:\n"
                "파일 열기\n"
                "첫 문장 번역\n"
                "10분 타이머\n"
                "끝나면 보고해."
            ),
            tool_calls=[],
        )


def build_provider(settings: Settings) -> LLMProvider:
    """build_provider

    Args:
        settings: 사용할 provider 종류가 선언된 애플리케이션 설정.

    Returns:
        LLMProvider: 설정된 모드에 맞는 초기화된 provider 구현체.
    """
    if settings.llm_provider == "openai":
        return OpenAIProvider(settings)
    if settings.llm_provider == "local":
        return LocalOpenAICompatibleProvider(settings)
    if settings.llm_provider == "scripted":
        return ScriptedFallbackProvider()
    raise ValueError(f"Unsupported llm provider: {settings.llm_provider}")


def _parse_local_tool_calls(output: str) -> tuple[list[ToolCall], str]:
    """_parse_local_tool_calls

    Args:
        output: 로컬 모델의 원문 출력 문자열.

    Returns:
        tuple[list[ToolCall], str]: 파싱된 tool call 목록과 정리된 일반 텍스트.
    """
    matches = re.findall(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", output, flags=re.DOTALL)
    tool_calls: list[ToolCall] = []
    for match in matches:
        try:
            payload = json.loads(match)
        except json.JSONDecodeError:
            continue
        name = payload.get("name")
        arguments = payload.get("arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}
        if isinstance(name, str) and isinstance(arguments, dict):
            tool_calls.append(ToolCall(id=f"local-{uuid.uuid4().hex[:10]}", name=name, arguments=arguments))

    cleaned = re.sub(r"<tool_call>\s*\{.*?\}\s*</tool_call>", "", output, flags=re.DOTALL).strip()
    return tool_calls, cleaned
