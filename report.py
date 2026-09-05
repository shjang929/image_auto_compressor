"""
report.py
압축 전/후 용량을 사람이 읽기 좋은 형태로 비교/요약하는 유틸리티.

GUI(gui.py)뿐 아니라 콘솔에서 결과를 확인하고 싶을 때도 재사용할 수 있도록
compressor.py의 BatchResult/FileResult와 분리해서 둔다.
"""
from __future__ import annotations

from compressor import BatchResult, FileResult


def format_bytes(n: float) -> str:
    """바이트 수를 KB/MB/GB 단위의 읽기 쉬운 문자열로 변환한다."""
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            if size <1024 or unit == "GB":
                if unit == "B":
                    return f"{int(size)}{unit}"
                return f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}TB"

def format_file_line(fr: FileResult) -> str:
    """파일 하나의 압축 전/후 용량 비교를 한 줄로 표현한다."""
    if fr.status != "OK":
        return f"[오류] {fr.src_path}: {fr.message}"
    return (
        f"{fr.src_path}: {format_bytes(fr.original_size)} -> "
        f"{format_bytes(fr.compressed_size)}"
        f"(-{fr.saved_percent:.1f}%, {format_bytes(fr.saved_bytes)} 절감)"
    )


def summarize(result: BatchResult) -> str:
    """폴더 전체 압축 결과를 요약 문자열로 만든다."""
    ok = sum(1 for f in result.files if f.status == "OK")
    err =sum(1 for f in result.files if f.status == "ERROR")
    return (
        f"총 {len(result.files)}개 파일 (성공 {ok}, 오류 {err})\n"
        f"원본 총 용량: {format_bytes(result.total_original)}\n"
        f"압축 후 총 용량: {format_bytes(result.total_compressed)}\n"
        f"절감량: {format_bytes(result.total_saved)} ({result.total_saved_percent:.1f}%)"
    )


def print_report(result: BatchResult) -> None:
    """콘솔에 파일별 비교 + 전체 요약을 출력한다."""
    for fr in result.files:
        print(format_file_line(fr))
    print("-" * 60)
    print(summarize(result))

if __name__ == "__main__":
    from compressor import compress_folder
    result = compress_folder("test_images", "test_output", quality=80)
    print_report(result)