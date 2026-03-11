"""
프로젝트 로컬 모델 초기화 스크립트.

기본 동작:
- Hugging Face의 `ahnhs2k/saya_rp_4b_v3`를 내려받는다.
- 저장 위치는 항상 `deadlineforyou/models/saya_rp_4b_v3`다.

사용 예시:
  uv run initialize.py
  uv run initialize.py --force
  uv run initialize.py --repo-id ahnhs2k/saya_rp_4b_v3
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from huggingface_hub import snapshot_download
from huggingface_hub.utils import HfHubHTTPError


ROOT_DIR = Path(__file__).resolve().parent
MODEL_DIR = ROOT_DIR / "deadlineforyou" / "models" / "saya_rp_4b_v3"
DEFAULT_REPO_ID = "ahnhs2k/saya_rp_4b_v3"


def looks_downloaded(target_dir: Path) -> bool:
    """looks_downloaded

    Args:
        target_dir: 모델이 저장될 대상 디렉터리.

    Returns:
        bool: 핵심 모델 파일과 설정 파일이 이미 있으면 True.
    """
    return (target_dir / "config.json").exists() and any(
        (target_dir / name).exists()
        for name in ("model.safetensors", "pytorch_model.bin", "tokenizer.json", "tokenizer_config.json")
    )


def download_model(repo_id: str, target_dir: Path, force: bool) -> Path:
    """download_model

    Args:
        repo_id: Hugging Face Hub 리포지토리 ID.
        target_dir: 모델을 내려받을 로컬 디렉터리.
        force: 기존 디렉터리가 있어도 다시 받을지 여부.

    Returns:
        Path: 다운로드가 완료된 로컬 디렉터리 경로.
    """
    if not force and looks_downloaded(target_dir):
        print(f"[SKIP] 이미 모델이 존재한다: {target_dir}")
        return target_dir

    if force and target_dir.exists():
        print(f"[CLEAN] 기존 모델 디렉터리를 제거한다: {target_dir}")
        shutil.rmtree(target_dir)

    target_dir.mkdir(parents=True, exist_ok=True)

    print(f"[DOWNLOAD] repo={repo_id}")
    print(f"[TARGET]   dir ={target_dir}")

    try:
        # local_dir를 직접 지정해 프로젝트가 기대하는 위치로 정확히 내려받는다.
        snapshot_download(
            repo_id=repo_id,
            local_dir=str(target_dir),
            local_dir_use_symlinks=False,
            revision="main",
        )
    except HfHubHTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        if status_code in (401, 403):
            raise RuntimeError(
                "모델 다운로드 권한이 없다. `huggingface-cli login` 후 다시 시도해라."
            ) from exc
        raise RuntimeError("모델 다운로드 중 HTTP 오류가 발생했다.") from exc

    print(f"[DONE] 모델 다운로드 완료: {target_dir}")
    return target_dir


def parse_args() -> argparse.Namespace:
    """parse_args

    Args:
        없음.

    Returns:
        argparse.Namespace: CLI 인자가 파싱된 결과.
    """
    parser = argparse.ArgumentParser(description="DeadlineForYou 로컬 모델 초기화")
    parser.add_argument(
        "--repo-id",
        default=DEFAULT_REPO_ID,
        help=f"내려받을 Hugging Face 리포지토리 ID. 기본값: {DEFAULT_REPO_ID}",
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
    MODEL_DIR.parent.mkdir(parents=True, exist_ok=True)
    downloaded_dir = download_model(args.repo_id, MODEL_DIR, args.force)

    print("")
    print("[READY] 로컬 모델 초기화 완료")
    print(f"repo_id   : {args.repo_id}")
    print(f"local_dir : {downloaded_dir}")
    print("이제 `.env`에서 DFY_LLM_PROVIDER=local 로 두고 서버를 실행하면 된다.")


if __name__ == "__main__":
    main()
