"""
compressor.py
이미지 폴더 전체를 스캔해서 자동으로 압축하는 핵심 로직.

이 모듈은 GUI(tkinter)와 분리되어 있어 커맨드라인이나 다른 스크립트에서도
그대로 재사용할 수 있다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path 
from typing import Callable, List, Optional

from PIL import Image

# 압축 대상으로 인식할 확장자
SUPPORTED_EXTENSIONS = {".png", ".jpg", "jpeg", ".bmp", "tiff", ".tif", ".webp"}

# 출력 포맷: "KEEP"(원본 형식 유지) | "JPG"(JPG로 변환) | "WEBP"(WebP로 변환)
Outputformat = str

# PNG 등 투명 배경을 JPG로 변환할 때 채울 배경색 (기본: 흰색)
DEFAULT_FATTEN_BG = (255, 255, 255)

@dataclass
class FileResult:
    """파일 한 개에 대한 압축 결과."""

    src_path: str
    dst_path: Optional[str]
    original_size: int
    compressed_size: int
    status: str # "OK" | "ERROR"
    message: str = ""

    @property
    def saved_bytes(self) -> int:
        return max(self.original_size - self.compressed_size, 0)

    @property
    def saved_percent(self) -> float:
        if self.original_size == 0:
            return 0.0
        return self.saved_bytes / self.original_size * 100

@dataclass
class BatchResult:
    """폴더 전체 압축 결과 모음."""

    files: List[FileResult] =field(default_factory=list)

    @property
    def total_original(self) -> int:
        return sum(f.original_size for f in self.files)

    @property
    def total_compressed(self) -> int:
        return sum(f.compressed_size for f in self.files if f.status == "OK")

    @property
    def total_saved(self) -> int:
        return max(self.total_original - self.total_compressed, 0)

    @property
    def total_saved_percent(self) -> float:
        if self.total_original == 0:
            return 0.0
        return self.total_saved /self.total_original * 100



def scan_images(folder: str, recursive: bool = True) -> List[Path]:
        """폴더에서 지원하는 이미지 파일을 전부 찾는다."""
        root = Path(folder)
        pattern = "**/*" if recursive else "*"
        files = [
            p for p in root.glob(pattern)
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
        ]
        return sorted(files)

def _build_dst_path(src: Path, src_root: Path, dst_root: Path, output_format: OutputFormat) -> Path:
        """원본 폴더 구조를 유지하면서 대상 경로를 만든다. 포맷 변환 시 확장자도 바꿔준다."""
        rel = src.relative_to(src_root)
        if output_format == "JPG":
            rel = rel.with_suffix(".jpg")
        elif output_format == "WEBP":
            rel = rel.with_suffix(".webp")
        return dst_root / rel



def _flatten_to_rgb(img: Image.Image, bg_color=DEFAULT_FATTEN_BG) -> Image.Image:
        """알파 채널(투명 배경)이 있는 이미지를 단색 배경 위에 합성해 RGB로 만든다.
        
        JPG는 투명도를 지원하지 않으므로 PNG -> JPG 변환 시 반드시 필요하다.
        """
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            rgba = img.convert("RGBA")
            background = Image.new("RGB", rgba.size, bg_color)
            background.paste(rgba, mask=rgba.split()[-1])
            return background
        return img.convert("RGB")


def compress_one(
        src: Path,
        dst: Path,
        quality: int = 60,
        output_format: Outputformat = "KEEP",
    ) -> FileResult:
        """이미지 한 장을 압축(및 필요 시 포맷 변환)해서 dst 경로에 저장한다."""
        original_size = src.stat().st_size
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            with Image.open(src) as img:
                img.load()
                ext = src.suffix.lower()

                if output_format == "JPG":
                    # PNG 등 투명 배경이 있는 이미지는 흰 배경으로 합성 후 JPG로 저장
                    img_to_save = _flatten_to_rgb(img)
                    img_to_save.save(dst, format="JPEG", quality=quality, optimize=True)
                elif output_format == "WEBP":
                    # WebP는 투명도를 지원하므로 별도 배경 합성 없이 그대로 저장
                    img.save(dst, format="WEBP", quality=quality, method=6)
                elif ext in (".jpg", ".jpeg"):
                    img_to_save = img.convert("RGB") if img.mode not in ("RGB", "L") else img
                    img_to_save.save(dst, format="JPEG", quality=quality, optimize=True)
                elif ext == ".webp":
                    img.save(dst, format="WEBP", quality=quality, method=6)
                elif ext == ".png":
                    img.save(dst, format="PNG", optimize=True)
                else:
                    # bmp, tiff 등은 재인코딩 없이 그대로 복사(추후 확장 가능)
                    img.save(dst, format=img.format or ext.lstrip("."))

            compressed_size = dst.stat().st_size
            return FileResult(str(src), str(dst), original_size, compressed_size, "OK")
        except Exception as exc: # noqa: BLE001 - 배치 처리 중 한 파일 오류로 전체가 죽으면 안 됨
            return FileResult(str(src), None, original_size, 0, "ERROR", str(exc))


def compress_folder(
        src_folder: str,
        dst_folder: str,
        quality: int = 80,
        output_format: Outputformat = "KEEP",
        recursive: bool = True,
        progress_cb: Optional[Callable[[int, int, FileResult], None]] = None,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> BatchResult:
        """폴더 전체를 스캔해서 순서대로 압축한다.

        progress_cb(현재 순번, 전체 개수, 방금 처리한 FileResult)로 진행 상황을 알려주고,
        should_cancel()이 True를 반환하면 즉시 중단한다.
        """
        src_root = Path(src_folder)
        dst_root = Path(dst_folder)
        files = scan_images(src_folder, recursive=recursive)
        result = BatchResult()
        total = len(files)

        for i, src in enumerate(files, start=1):
            if should_cancel and should_cancel():
                break
            dst = _build_dst_path(src, src_root, dst_root, output_format)
            file_result = compress_one(src, dst, quality=quality, output_format=output_format)
            result.files.append(file_result)
            if progress_cb:
                progress_cb(i, total, file_result)

        return result

if __name__ == "__main__":
    result = compress_folder("test_images", "test_output", quality=80)
    for f in result.files:
        print(f)
    print("원본:", result.total_original, "압축후:", result.total_compressed)
                
