"""
프로젝트 로컬 모델 초기화 스크립트.

기본 동작:
- 코칭용 `Qwen/Qwen3-4B-Instruct-2507`를 내려받는다.
- 번역용 `yanolja/YanoljaNEXT-Rosetta-4B`를 내려받는다.
- 선택적으로 이미지용 `stabilityai/sdxl-turbo`도 내려받을 수 있다.

저장 위치:
- coach_qwen  -> `deadlineforyou/models/qwen3_4b_instruct`
- translation -> `deadlineforyou/models/rosetta_4b`
- image       -> `deadlineforyou/models/sdxl_turbo`

사용 예시:
  uv run initialize.py
  uv run initialize.py --target coach_qwen
  uv run initialize.py --target translation
  uv run initialize.py --target image
  uv run initialize.py --target all --force
"""

from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass
from pathlib import Path

from huggingface_hub import snapshot_download
from huggingface_hub.utils import HfHubHTTPError


ROOT_DIR = Path(__file__).resolve().parent
MODELS_ROOT = ROOT_DIR / "deadlineforyou" / "models"


@dataclass(frozen=True, slots=True)
class ModelSpec:
    key: str
    repo_id: str
    target_dir: Path
    description: str


MODEL_SPECS: dict[str, ModelSpec] = {
    "coach_qwen": ModelSpec(
        key="coach_qwen",
        repo_id="Qwen/Qwen3-4B-Instruct-2507",
        target_dir=MODELS_ROOT / "qwen3_4b_instruct",
        description="기본 Qwen3 코칭 모델",
    ),
    "translation": ModelSpec(
        key="translation",
        repo_id="yanolja/YanoljaNEXT-Rosetta-4B",
        target_dir=MODELS_ROOT / "rosetta_4b",
        description="번역 전용 로컬 모델",
    ),
    "image": ModelSpec(
        key="image",
        repo_id="stabilityai/sdxl-turbo",
        target_dir=MODELS_ROOT / "sdxl_turbo",
        description="가벼운 이미지 생성용 로컬 모델",
    ),
}


def looks_downloaded(target_dir: Path) -> bool:
    """looks_downloaded

    Args:
        target_dir: 모델이 저장될 대상 디렉터리.

    Returns:
        bool: 핵심 설정 파일과 가중치 또는 토크나이저 파일이 있으면 True.
    """
    if not (target_dir / "config.json").exists():
        return False
    return any(
        (target_dir / name).exists()
        for name in (
            "model.safetensors",
            "model.safetensors.index.json",
            "pytorch_model.bin",
            "tokenizer.json",
            "tokenizer_config.json",
        )
    )


def download_model(spec: ModelSpec, force: bool) -> Path:
    """download_model

    Args:
        spec: 내려받을 모델 명세.
        force: 기존 디렉터리가 있어도 다시 받을지 여부.

    Returns:
        Path: 다운로드가 완료된 로컬 디렉터리 경로.
    """
    target_dir = spec.target_dir
    if not force and looks_downloaded(target_dir):
        print(f"[SKIP] {spec.key}: 이미 모델이 존재한다: {target_dir}")
        return target_dir

    if force and target_dir.exists():
        print(f"[CLEAN] {spec.key}: 기존 모델 디렉터리를 제거한다: {target_dir}")
        shutil.rmtree(target_dir)

    target_dir.mkdir(parents=True, exist_ok=True)

    print(f"[DOWNLOAD] target={spec.key}")
    print(f"[REPO]     repo={spec.repo_id}")
    print(f"[TARGET]   dir ={target_dir}")
    print(f"[DESC]     {spec.description}")

    try:
        # local_dir를 직접 지정해 프로젝트가 기대하는 위치로 정확히 내려받는다.
        snapshot_download(
            repo_id=spec.repo_id,
            local_dir=str(target_dir),
            local_dir_use_symlinks=False,
            revision="main",
        )
    except HfHubHTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        if status_code in (401, 403):
            raise RuntimeError(
                f"{spec.repo_id} 다운로드 권한이 없다. `huggingface-cli login` 후 다시 시도해라."
            ) from exc
        raise RuntimeError(f"{spec.repo_id} 다운로드 중 HTTP 오류가 발생했다.") from exc

    print(f"[DONE] {spec.key}: 모델 다운로드 완료: {target_dir}")
    return target_dir


def resolve_specs(target: str) -> list[ModelSpec]:
    """resolve_specs

    Args:
        target: CLI에서 선택한 모델 그룹.

    Returns:
        list[ModelSpec]: 실제로 다운로드할 모델 명세 목록.
    """
    if target == "core":
        return [MODEL_SPECS["coach"], MODEL_SPECS["translation"]]
    if target == "all":
        return list(MODEL_SPECS.values())
    return [MODEL_SPECS[target]]


def parse_args() -> argparse.Namespace:
    """parse_args

    Args:
        없음.

    Returns:
        argparse.Namespace: CLI 인자가 파싱된 결과.
    """
    parser = argparse.ArgumentParser(description="DeadlineForYou 로컬 모델 초기화")
    parser.add_argument(
        "--target",
        choices=["core", "coach", "coach_qwen", "translation", "image", "all"],
        default="core",
        help="다운로드할 모델 묶음. 기본값은 coach+translation인 core.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="기존 모델 디렉터리가 있어도 삭제 후 다시 다운로드한다.",
    )
    return parser.parse_args()


def main() -> None:
    """main

    Args:
        없음.

    Returns:
        None: 초기화 스크립트를 실행하고 다운로드 결과를 출력한다.
    """
    args = parse_args()
    MODELS_ROOT.mkdir(parents=True, exist_ok=True)
    specs = resolve_specs(args.target)

    print(f"[START] target={args.target}")
    print("")

    downloaded: list[tuple[str, Path, str]] = []
    for spec in specs:
        downloaded_dir = download_model(spec, args.force)
        downloaded.append((spec.key, downloaded_dir, spec.repo_id))
        print("")

    print("[READY] 로컬 모델 초기화 완료")
    for key, local_dir, repo_id in downloaded:
        print(f"- {key}: {repo_id} -> {local_dir}")
    print("")
    print("이제 `.env`를 확인하고 서버를 실행하면 된다.")


if __name__ == "__main__":
    main()
