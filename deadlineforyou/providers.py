from __future__ import annotations

from abc import ABC, abstractmethod

from openai import OpenAI
from transformers import AutoModelForCausalLM, AutoTokenizer

from deadlineforyou.config import Settings


class LLMProvider(ABC):
    @abstractmethod
    def generate(self, system_prompt: str, context_block: str, history: list[dict[str, str]], user_message: str) -> str:
        """generate

        Args:
            system_prompt: 기본 페르소나와 행동 규칙.
            context_block: 실행 시점 상태가 담긴 컨텍스트 블록.
            history: 최근 대화 기록.
            user_message: 최신 사용자 입력.

        Returns:
            str: 어시스턴트 응답 문자열.
        """
        raise NotImplementedError


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

    def generate(self, system_prompt: str, context_block: str, history: list[dict[str, str]], user_message: str) -> str:
        """generate

        Args:
            system_prompt: 기본 페르소나와 행동 규칙.
            context_block: 실행 시점 상태가 담긴 컨텍스트 블록.
            history: 최근 대화 기록.
            user_message: 최신 사용자 입력.

        Returns:
            str: OpenAI가 생성한 코칭 메시지.
        """
        # 시스템 메시지에 규칙과 상태를 먼저 고정해 두어 대화 이력이 이를 덮어쓰지 못하게 한다.
        messages = [{"role": "system", "content": f"{system_prompt}\n\n{context_block}"}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})
        response = self.client.chat.completions.create(model=self.model, messages=messages)
        return (response.choices[0].message.content or "").strip()


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
        # 모델 디렉터리에 chat template이 포함되어 있어 transformers 직로딩만으로 충분하다.
        self.tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_path,
            trust_remote_code=True,
            device_map=settings.local_device_map,
            torch_dtype="auto",
        )
        self.max_new_tokens = settings.local_max_new_tokens
        self.temperature = settings.local_temperature

    def generate(self, system_prompt: str, context_block: str, history: list[dict[str, str]], user_message: str) -> str:
        """generate

        Args:
            system_prompt: 기본 페르소나와 행동 규칙.
            context_block: 실행 시점 상태가 담긴 컨텍스트 블록.
            history: 최근 대화 기록.
            user_message: 최신 사용자 입력.

        Returns:
            str: 내장된 Qwen3 체크포인트가 생성한 코칭 메시지.
        """
        messages = [{"role": "system", "content": f"{system_prompt}\n\n{context_block}"}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})
        # 모델이 기대하는 원래 채팅 포맷으로 렌더링해 Saya 말투와 응답 형식을 안정적으로 유지한다.
        prompt = self.tokenizer.apply_chat_template(
            messages,
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
        return output.strip()


class ScriptedFallbackProvider(LLMProvider):
    def generate(self, system_prompt: str, context_block: str, history: list[dict[str, str]], user_message: str) -> str:
        """generate

        Args:
            system_prompt: 기본 페르소나와 행동 규칙.
            context_block: 실행 시점 상태가 담긴 컨텍스트 블록.
            history: 최근 대화 기록.
            user_message: 최신 사용자 입력.

        Returns:
            str: 모델 없이 로컬 테스트를 할 때 쓰는 고정 응답.
        """
        del system_prompt, history
        return (
            "그래서 지금 번역은 했어?\n"
            f"{context_block.splitlines()[-1]}\n"
            "지금 할 일:\n"
            "파일 열기\n"
            "첫 문장 번역\n"
            "10분 타이머\n"
            "끝나면 보고해."
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
