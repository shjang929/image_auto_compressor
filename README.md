
# 이미지 자동 압축기

폴더 안의 이미지를 한 번에 스캔해서 압축하고, 필요하면 JPG나 WebP로 변환해주는 tkinter 기반 GUI 도구입니다.

## 주요 기능

- 폴더 전체 자동 압축 (하위 폴더 포함 옵션)
- PNG → JPG 변환 (투명 배경은 흰색으로 채워서 저장)
- WebP 변환 (투명도 유지)
- 압축 전/후 용량 비교 (파일별 결과 + 전체 요약 리포트)
- tkinter GUI로 폴더 선택, 품질 조절, 진행 상황 확인, 결과 테이블 확인

## 실행 방법
이 프로젝트는 [uv](https://docs.astral.sh/uv/)로 의존성을 관리합니다.

```bash
uv sync
python main.py
```

## 프로젝트 구조

- `compressor.py` — 이미지 압축·변환 핵심 로직
- `report.py` — 압축 결과를 사람이 읽기 쉬운 형태로 요약
- `gui.py` — tkinter 기반 화면 구성
- `main.py` — 실행 진입점

## 개발 배경

두 번째 토이 프로젝트로, git의 `main` / `dev` / `feature` 브랜치 전략과 pull request 기반 병합 흐름을 직접 연습하기 위해 만들었습니다.

- `main`: 안정 버전
- `dev`: 기능 통합 브랜치
- `feature`: 기능 개발 브랜치 (완료되면 PR로 `dev`에 병합)

`dev`가 충분히 안정화되면 `dev`를 `main`으로 병합합니다.
