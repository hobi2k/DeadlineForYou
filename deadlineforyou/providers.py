from __future__ import annotations

import json
import re
import uuid
from abc import ABC, abstractmethod
import gc
from pathlib import Path
from typing import Any

from transformers import AutoModelForCausalLM, AutoTokenizer, PreTrainedTokenizerFast
from transformers.models.gemma.tokenization_gemma import GemmaTokenizer
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


class TranslationProvider(ABC):
    @abstractmethod
    def translate_text(
        self,
        text: str,
        source_language: str,
        target_language: str,
        style: str,
    ) -> dict[str, Any]:
        """translate_text

        Args:
            text: 번역할 원문.
            source_language: 원문 언어.
            target_language: 목표 언어.
            style: 번역 스타일 힌트.

        Returns:
            dict[str, Any]: 번역 결과와 메타데이터.
        """
        raise NotImplementedError

    def unload(self) -> None:
        """unload

        Args:
            없음.

        Returns:
            None: 필요 시 provider가 잡고 있는 메모리를 해제한다.
        """
        return None


class ImageProvider(ABC):
    @abstractmethod
    def generate_image(self, prompt: str, size: str, style: str) -> dict[str, Any]:
        """generate_image

        Args:
            prompt: 이미지 생성 프롬프트.
            size: 생성 이미지 크기.
            style: 이미지 스타일 힌트.

        Returns:
            dict[str, Any]: 이미지 생성 결과.
        """
        raise NotImplementedError

    def unload(self) -> None:
        """unload

        Args:
            없음.

        Returns:
            None: 필요 시 provider가 잡고 있는 메모리를 해제한다.
        """
        return None


class LocalLLMProvider(LLMProvider):
    def __init__(
        self,
        settings: Settings,
        model_path: Path | None = None,
        max_new_tokens: int | None = None,
        temperature: float | None = None,
    ) -> None:
        """__init__

        Args:
            settings: 로컬 모델 로딩 옵션이 담긴 애플리케이션 설정.
            model_path: 선택적으로 덮어쓸 로컬 모델 경로.
            max_new_tokens: 선택적으로 덮어쓸 최대 생성 토큰 수.
            temperature: 선택적으로 덮어쓸 샘플링 온도.

        Returns:
            None: 토크나이저와 모델을 메모리에 적재한다.
        """
        resolved_model_path = settings.local_model_path if model_path is None else model_path
        if not resolved_model_path.exists():
            raise ValueError(f"Local model path does not exist: {resolved_model_path}")
        config_path = resolved_model_path / "config.json"
        model_type = ""
        if config_path.exists():
            with config_path.open("r", encoding="utf-8") as config_file:
                model_type = json.load(config_file).get("model_type", "")

        # Qwen 계열 체크포인트는 현재 환경의 AutoTokenizer 경로에서
        # fast tokenizer 충돌이 날 수 있어 slow Qwen2Tokenizer를 직접 사용한다.
        if model_type in {"qwen2", "qwen3"}:
            self.tokenizer = Qwen2Tokenizer.from_pretrained(
                resolved_model_path,
                trust_remote_code=True,
            )
        else:
            self.tokenizer = AutoTokenizer.from_pretrained(
                resolved_model_path,
                trust_remote_code=True,
                use_fast=False,
            )
        self.model = AutoModelForCausalLM.from_pretrained(
            resolved_model_path,
            trust_remote_code=True,
            device_map=settings.local_device_map,
            dtype="auto",
        )
        self.max_new_tokens = settings.local_max_new_tokens if max_new_tokens is None else max_new_tokens
        self.temperature = settings.local_temperature if temperature is None else temperature

    def _model_input_device(self) -> Any:
        """_model_input_device

        Args:
            없음.

        Returns:
            Any: 입력 텐서를 올릴 실제 디바이스.
        """
        for parameter in self.model.parameters():
            if parameter.device.type != "meta":
                return parameter.device
        return self.model.device

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
        model_inputs = self.tokenizer([prompt], return_tensors="pt").to(self._model_input_device())
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

    def unload(self) -> None:
        """unload

        Args:
            없음.

        Returns:
            None: 로컬 LLM이 점유한 메모리를 해제한다.
        """
        model = getattr(self, "model", None)
        tokenizer = getattr(self, "tokenizer", None)
        if model is not None:
            del self.model
        if tokenizer is not None:
            del self.tokenizer
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:  # pragma: no cover
            return


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


class InheritedTranslationProvider(TranslationProvider):
    def __init__(self, provider: LLMProvider, provider_name: str) -> None:
        """__init__

        Args:
            provider: 코칭에 쓰는 기본 LLM provider.
            provider_name: 응답 메타데이터에 넣을 provider 이름.

        Returns:
            None: 코칭 provider 재사용용 번역 provider를 초기화한다.
        """
        self.provider = provider
        self.provider_name = provider_name

    def translate_text(
        self,
        text: str,
        source_language: str,
        target_language: str,
        style: str,
    ) -> dict[str, Any]:
        """translate_text

        Args:
            text: 번역할 원문.
            source_language: 원문 언어.
            target_language: 목표 언어.
            style: 번역 스타일 힌트.

        Returns:
            dict[str, Any]: 번역 결과와 메타데이터.
        """
        translation_prompt = (
            "너는 전문 번역가다.\n"
            f"원문 언어: {source_language}\n"
            f"목표 언어: {target_language}\n"
            f"스타일: {style}\n"
            "설명 없이 번역문만 출력하라."
        )
        result = self.provider.generate_turn(
            system_prompt=translation_prompt,
            context_block="",
            messages=[{"role": "user", "content": text}],
            tools=None,
        )
        return {
            "provider": self.provider_name,
            "source_language": source_language,
            "target_language": target_language,
            "style": style,
            "translated_text": result.text.strip(),
        }


class LazyLocalTranslationProvider(TranslationProvider):
    def __init__(self, settings: Settings) -> None:
        """__init__

        Args:
            settings: 번역용 로컬 모델 설정.

        Returns:
            None: 번역 전용 provider 설정을 저장한다.
        """
        self.settings = settings
        self._tokenizer: Any | None = None
        self._model: Any | None = None

    def _load_model_components(self) -> tuple[Any, Any]:
        """_load_model_components

        Args:
            없음.

        Returns:
            tuple[Any, Any]: 번역에 사용할 토크나이저와 모델.
        """
        if self._tokenizer is None or self._model is None:
            model_path = self.settings.translation_local_model_path
            tokenizer = GemmaTokenizer.from_pretrained(model_path)
            if isinstance(tokenizer, bool) or not callable(tokenizer):
                tokenizer = PreTrainedTokenizerFast(
                    tokenizer_file=str(model_path / "tokenizer.json"),
                    bos_token="<bos>",
                    eos_token="<end_of_turn>",
                    pad_token="<pad>",
                    unk_token="<unk>",
                    additional_special_tokens=["<start_of_turn>", "<end_of_turn>"],
                )
            self._tokenizer = tokenizer
            self._model = AutoModelForCausalLM.from_pretrained(
                model_path,
                trust_remote_code=True,
                device_map=self.settings.local_device_map,
                dtype="auto",
            )
        return self._tokenizer, self._model

    def _model_input_device(self) -> Any:
        """_model_input_device

        Args:
            없음.

        Returns:
            Any: 입력 텐서를 올릴 실제 디바이스.
        """
        if self._model is None:
            raise RuntimeError("번역 모델이 아직 로드되지 않았다.")
        for parameter in self._model.parameters():
            if parameter.device.type != "meta":
                return parameter.device
        return self._model.device

    def translate_text(
        self,
        text: str,
        source_language: str,
        target_language: str,
        style: str,
    ) -> dict[str, Any]:
        """translate_text

        Args:
            text: 번역할 원문.
            source_language: 원문 언어.
            target_language: 목표 언어.
            style: 번역 스타일 힌트.

        Returns:
            dict[str, Any]: 번역 결과와 메타데이터.
        """
        translation_prompt = (
            "<bos><start_of_turn>instruction\n"
            f"Translate the user's text to {target_language}.\n"
            f"Source language: {source_language}\n"
            f"Style: {style}\n"
            "Provide the final translation immediately without any other text."
            "<end_of_turn>\n"
            "<start_of_turn>source\n"
            f"{text}<end_of_turn>\n"
            "<start_of_turn>translation\n"
        )
        tokenizer, model = self._load_model_components()
        model_inputs = tokenizer([translation_prompt], return_tensors="pt")
        # Gemma3 기반 Rosetta는 generate 호출에서 token_type_ids를 사용하지 않는다.
        # 일부 토크나이저 구현은 이 값을 같이 내보내므로, 생성 전에 제거해 호환성을 맞춘다.
        model_inputs.pop("token_type_ids", None)
        model_inputs = model_inputs.to(self._model_input_device())
        generated_ids = model.generate(
            **model_inputs,
            max_new_tokens=self.settings.translation_local_max_new_tokens,
            do_sample=True,
            temperature=self.settings.translation_local_temperature,
            top_p=0.9,
        )
        completion_ids = generated_ids[:, model_inputs.input_ids.shape[1]:]
        translated_text = tokenizer.batch_decode(completion_ids, skip_special_tokens=True)[0].strip()
        return {
            "provider": "local",
            "source_language": source_language,
            "target_language": target_language,
            "style": style,
            "translated_text": translated_text,
        }

    def unload(self) -> None:
        """unload

        Args:
            없음.

        Returns:
            None: 번역 모델이 점유한 메모리를 해제한다.
        """
        if self._model is not None:
            del self._model
            self._model = None
        if self._tokenizer is not None:
            del self._tokenizer
            self._tokenizer = None
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:  # pragma: no cover
            return


class ScriptedTranslationProvider(TranslationProvider):
    def translate_text(
        self,
        text: str,
        source_language: str,
        target_language: str,
        style: str,
    ) -> dict[str, Any]:
        """translate_text

        Args:
            text: 번역할 원문.
            source_language: 원문 언어.
            target_language: 목표 언어.
            style: 번역 스타일 힌트.

        Returns:
            dict[str, Any]: 테스트용 번역 결과.
        """
        return {
            "provider": "scripted",
            "source_language": source_language,
            "target_language": target_language,
            "style": style,
            "translated_text": text,
        }


class LocalSDXLTurboProvider(ImageProvider):
    def __init__(self, settings: Settings) -> None:
        """__init__

        Args:
            settings: 로컬 이미지 모델 설정.

        Returns:
            None: SDXL-Turbo 이미지 provider 설정을 저장한다.
        """
        self.settings = settings
        self.pipeline: Any | None = None
        if not self.settings.image_lazy_load:
            self._get_pipeline()

    def _parse_image_size(self, size: str) -> tuple[int, int]:
        """_parse_image_size

        Args:
            size: `512x512` 같은 `너비x높이` 형식의 크기 문자열.

        Returns:
            tuple[int, int]: 너비와 높이.
        """
        try:
            width_str, height_str = size.lower().split("x", maxsplit=1)
            width = int(width_str)
            height = int(height_str)
        except ValueError as exc:
            raise ValueError("이미지 크기는 512x512 같은 너비x높이 형식이어야 한다.") from exc

        pixel_area = width * height
        min_area = 512 * 512
        max_area = 1024 * 1024
        if pixel_area < min_area or pixel_area > max_area:
            raise ValueError("SDXL-Turbo 기준 총 픽셀 수는 512x512 이상 1024x1024 이하여야 한다.")
        return width, height

    def _build_output_path(self) -> Path:
        """_build_output_path

        Args:
            없음.

        Returns:
            Path: 생성 이미지를 저장할 경로.
        """
        filename = f"image_{uuid.uuid4().hex[:12]}.png"
        return self.settings.image_output_dir / filename

    def _get_pipeline(self) -> Any:
        """_get_pipeline

        Args:
            없음.

        Returns:
            Any: SDXL-Turbo 파이프라인 인스턴스.
        """
        if self.pipeline is not None:
            return self.pipeline

        try:
            import torch
            from diffusers import AutoPipelineForText2Image
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("로컬 이미지 생성에는 diffusers와 torch가 필요하다.") from exc

        model_path = self.settings.image_local_model_path
        if not model_path.exists():
            raise RuntimeError(f"로컬 이미지 모델 경로가 없다: {model_path}")

        self.pipeline = AutoPipelineForText2Image.from_pretrained(
            model_path,
            torch_dtype=torch.float16 if self.settings.image_device == "cuda" else torch.float32,
            use_safetensors=True,
        )
        if self.settings.image_device == "cuda" and self.settings.image_enable_model_cpu_offload:
            self.pipeline.enable_model_cpu_offload()
        else:
            self.pipeline = self.pipeline.to(self.settings.image_device)
        return self.pipeline

    def unload(self) -> None:
        """unload

        Args:
            없음.

        Returns:
            None: 이미지 파이프라인 메모리를 해제한다.
        """
        if self.pipeline is None:
            return

        pipeline = self.pipeline
        self.pipeline = None
        del pipeline
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:  # pragma: no cover
            return

    def generate_image(self, prompt: str, size: str, style: str) -> dict[str, Any]:
        """generate_image

        Args:
            prompt: 이미지 생성 프롬프트.
            size: 생성 이미지 크기.
            style: 이미지 스타일 힌트.

        Returns:
            dict[str, Any]: 이미지 생성 결과.
        """
        normalized_prompt = prompt.strip()
        if not normalized_prompt:
            return {"error": "invalid_prompt", "message": "이미지 프롬프트가 비었다."}

        try:
            width, height = self._parse_image_size(size)
        except ValueError as exc:
            return {"error": "invalid_image_size", "message": str(exc)}

        try:
            import torch
        except ImportError as exc:  # pragma: no cover
            return {
                "error": "missing_torch",
                "message": f"로컬 이미지 생성에 필요한 torch를 불러오지 못했다: {exc}",
            }

        output_path: Path | None = None
        try:
            pipeline = self._get_pipeline()
            generator_device = "cpu" if self.settings.image_enable_model_cpu_offload else self.settings.image_device
            generator = torch.Generator(device=generator_device).manual_seed(self.settings.image_seed)
            final_prompt = f"{normalized_prompt}, {style} style" if style else normalized_prompt
            negative_prompt = self.settings.image_negative_prompt or None
            result = pipeline(
                prompt=final_prompt,
                negative_prompt=negative_prompt,
                width=width,
                height=height,
                num_inference_steps=self.settings.image_num_inference_steps,
                guidance_scale=self.settings.image_guidance_scale,
                generator=generator,
            )
            image = result.images[0]
            output_path = self._build_output_path()
            image.save(output_path)
        except Exception as exc:  # noqa: BLE001
            return {
                "error": "image_generation_failed",
                "message": f"SDXL-Turbo 로컬 생성에 실패했다: {exc}",
            }
        finally:
            if self.settings.image_unload_after_generation:
                self.unload()

        return {
            "provider": "local",
            "prompt": normalized_prompt,
            "style": style,
            "size": f"{width}x{height}",
            "file_path": str(output_path),
        }


class DisabledImageProvider(ImageProvider):
    def generate_image(self, prompt: str, size: str, style: str) -> dict[str, Any]:
        """generate_image

        Args:
            prompt: 이미지 생성 프롬프트.
            size: 생성 이미지 크기.
            style: 이미지 스타일 힌트.

        Returns:
            dict[str, Any]: 비활성화 상태 안내 결과.
        """
        del prompt, size, style
        return {
            "error": "image_provider_not_configured",
            "message": "이미지 생성은 별도 모델이 필요하다. 현재는 DFY_IMAGE_PROVIDER=local 로 설정해야 한다.",
        }


def build_provider(settings: Settings) -> LLMProvider:
    """build_provider

    Args:
        settings: 사용할 provider 종류가 선언된 애플리케이션 설정.

    Returns:
        LLMProvider: 설정된 모드에 맞는 초기화된 provider 구현체.
    """
    if settings.llm_provider == "local":
        return LocalLLMProvider(settings)
    if settings.llm_provider == "scripted":
        return ScriptedFallbackProvider()
    raise ValueError(f"Unsupported llm provider: {settings.llm_provider}")


def build_translation_provider(
    settings: Settings,
    fallback_provider: LLMProvider | None = None,
) -> TranslationProvider:
    """build_translation_provider

    Args:
        settings: 번역 전용 provider 선택이 담긴 애플리케이션 설정.
        fallback_provider: `inherit` 모드에서 재사용할 기본 provider.

    Returns:
        TranslationProvider: 번역 요청 전용 provider 구현체.
    """
    if settings.translation_provider in {"inherit", "same"}:
        provider = fallback_provider if fallback_provider is not None else build_provider(settings)
        return InheritedTranslationProvider(provider, provider_name=settings.llm_provider)
    if settings.translation_provider == "local":
        provider = LazyLocalTranslationProvider(settings)
        if not settings.translation_lazy_load:
            provider._load_model_components()
        return provider
    if settings.translation_provider == "scripted":
        return ScriptedTranslationProvider()
    raise ValueError(f"Unsupported translation provider: {settings.translation_provider}")


def build_image_provider(settings: Settings) -> ImageProvider:
    """build_image_provider

    Args:
        settings: 이미지 provider 선택이 담긴 애플리케이션 설정.

    Returns:
        ImageProvider: 이미지 생성 전용 provider 구현체.
    """
    if settings.image_provider == "local":
        return LocalSDXLTurboProvider(settings)
    if settings.image_provider == "none":
        return DisabledImageProvider()
    raise ValueError(f"Unsupported image provider: {settings.image_provider}")


def _parse_local_tool_calls(output: str) -> tuple[list[ToolCall], str]:
    """_parse_local_tool_calls

    Args:
        output: 로컬 모델의 원문 출력 문자열.

    Returns:
        tuple[list[ToolCall], str]: 파싱된 tool call 목록과 정리된 일반 텍스트.
    """
    blocks: list[str] = []
    for pattern in (
        r"<tool_call>\s*(.*?)\s*</tool_call>",
        r"<function_call>\s*(.*?)\s*</function_call>",
        r"```json\s*(\{.*?\}|\[.*?\])\s*```",
    ):
        blocks.extend(re.findall(pattern, output, flags=re.DOTALL))

    tool_calls: list[ToolCall] = []
    for block in blocks:
        payload_text = block.strip()
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            continue

        payloads = payload if isinstance(payload, list) else [payload]
        for item in payloads:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            arguments = item.get("arguments", {})
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {}
            if isinstance(name, str) and isinstance(arguments, dict):
                tool_calls.append(ToolCall(id=f"local-{uuid.uuid4().hex[:10]}", name=name, arguments=arguments))

    cleaned = output
    for pattern in (
        r"<tool_call>\s*(.*?)\s*</tool_call>",
        r"<function_call>\s*(.*?)\s*</function_call>",
        r"```json\s*(\{.*?\}|\[.*?\])\s*```",
    ):
        cleaned = re.sub(pattern, "", cleaned, flags=re.DOTALL)
    cleaned = cleaned.strip()
    return tool_calls, cleaned
