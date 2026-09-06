"""
gui.py
tkinter 기반 GUI.

무거운 압축 작업은 별도 스레드에서 실행하고, 진행 상황은 큐(Queue)를 통해
메인 스레드(UI)로 전달한다. tkinter 위젯은 메인 스레드에서만 건드려야 하므로
워커 스레드에서 직접 위젯을 수정하지 않고 항상 큐에 메시지를 넣는 방식을 쓴다.
"""
from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from compressor import BatchResult, FileResult, compress_folder
from report import format_bytes

FORMAT_LABELS = {
    "KEEP": "원본 형식 유지 (압축만)",
    "JPG": "JPG로 변환",
    "WEBP": "WebP로 변환",
}
LABEL_TO_FORMAT = {v: k for k, v in FORMAT_LABELS.items()}


class ImageCompressorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("이미지 자동 압축기")
        root.geometry("900x620")
        root.minsize(780, 540)

        self.src_folder = tk.StringVar()
        self.dst_folder = tk.StringVar()
        self.quality = tk.StringVar()
        self.quality = tk.IntVar(value=80)
        self.recursive = tk.BooleanVar(value=True)

        self.worker_thread: threading.Thread | None = None
        self.cancel_flag = False
        self.msg_queue = queue.Queue()

        self._build_widgets()
        self.root.after(100, self._poll_queue)

    # --------------------------------------------------------------------------
    # UI 구성
    # ---------------------------------------------------------------------------
    def _build_widgets(self):
        pad = {"padx": 8, "pady": 6}

        folder_frame = ttk.LabelFrame(self.root, text="폴더 선택")
        folder_frame.pack(fill="x", **pad)
        folder_frame.columnconfigure(1, weight=1)

        ttk.Label(folder_frame, text="원본 폴더").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        ttk.Entry(folder_frame, textvariable=self.src_folder).grid(row=0, column=1, sticky="we", padx=6)
        ttk.Button(folder_frame, text="찾아보기", command=self._pick_src).grid(row=0, column=2, padx=6)

        ttk.Label(folder_frame, text="저장 폴더").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        ttk.Entry(folder_frame, textvariable=self.dst_folder).grid(row=1, column=1, sticky="we", padx=6)
        ttk.Button(folder_frame, text="찾아보기", command=self._pick_dst).grid(row=1, column=2, padx=6)

        opt_frame = ttk.LabelFrame(self.root, text="옵션")
        opt_frame.pack(fill="x", **pad)

        ttk.Label(opt_frame, text="출력 형식").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        self.fmt_combo = ttk.Combobox(
            opt_frame, state="readonly", width=24, values=list(FORMAT_LABELS.values())
        )
        self.fmt_combo.set(FORMAT_LABELS["KEEP"])
        self.fmt_combo.grid(row=0, column=1, sticky="w", padx=6)

        ttk.Label(opt_frame, text="품질").grid(row=0, column=2, sticky="w", padx=(24, 6))
        quality_scale = ttk.Scale(
            opt_frame, from_=10, to=100, variable=self.quality, orient="horizontal", length=160,
            command=self._on_quality_change,      
        )
        quality_scale.grid(row=0, column=3, sticky="w", padx=6)
        self.quality_value_label = ttk.Label(opt_frame, text="80", width=3)
        self.quality_value_label.grid(row=0, column=4, sticky="w")

        ttk.Checkbutton(opt_frame, text="하위 폴더 포함", variable=self.recursive).grid(
            row=0, column=5, sticky="w", padx=(24, 6)
        )

        run_frame = ttk.Frame(self.root)
        run_frame.pack(fill="x", **pad)

        self.run_button = ttk.Button(run_frame, text="압축 시작", command=self._start)
        self.run_button.pack(side="left")
        self.cancel_button = ttk.Button(run_frame, text="취소", command=self._cancel, state="disabled")
        self.cancel_button.pack(side="left", padx=8)

        self.progress= ttk.Progressbar(run_frame, mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=12)

        self.status_label = ttk.Label(run_frame, text="대기 중", width=14)
        self.status_label.pack(side="left", padx=8)

        table_frame = ttk.LabelFrame(self.root, text="파일별 결과")
        table_frame.pack(fill="both", expand=True, **pad)

        columns = ("file", "original", "compressed", "saved", "status")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=14)
        headings = {
            "file": "파일명",
            "original": "원본 용량",
            "compressed": "압축 후 용량",
            "saved": "절감률",
            "status": "상태",
        }
        widths = {"file": 340, "original": 110, "compressed": 120, "saved": 90, "status": 140}
        for col in columns:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, width=widths[col], anchor="w")
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.summary_label = ttk.Label(
            self.root, text="압축 전/후 용량 비교가 여기에 표시됩니다.", font=("", 10, "bold")
        )
        self.summary_label.pack(fill="x", padx=8, pady=(0, 10))

    def _on_quality_change(self, value):
        self.quality_value_label.configure(text=str(int(float(value))))

    #-----------------------------------------------------------------
    # 이벤트 핸들러
    #-----------------------------------------------------------------
    def _pick_src(self):
        folder = filedialog.askdirectory(title="원본 폴더 선택")
        if folder:
            self.src_folder.set(folder)
            if not self.dst_folder.get():
                parent = os.path.dirname(folder)
                base_name = os.path.basename(folder)
                self.dst_folder.set(os.path.join(parent, f"{base_name}_compressed"))

    def _pick_dst(self):
        folder = filedialog.askdirectory(title="저장 폴더 선택")
        if folder:
            self.dst_folder.set(folder)

    def _start(self):
        src = self.src_folder.get().strip()
        dst = self.dst_folder.get().strip()

        if not src or not os.path.isdir(src):
            messagebox.showwarning("경고", "올바른 원본 폴더를 선택해주세요.")
            return
        if not dst:
            messagebox.showwarning("경고", "저장 폴더를 선택해주세요.")
            return
        if os.path.abspath(src) == os.path.abspath(dst):
            messagebox.showwarning("경고", "원본 폴더와 저장 폴더는 달라야 합니다.")
            return

        output_format = LABEL_TO_FORMAT.get(self.fmt_combo.get(), "KEEP")

        self.tree.delete(*self.tree.get_children())
        self.summary_label.configure(text="처리 중...")
        self.progress.configure(value=0, maximum=100)
        self.run_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.status_label.configure(text="스캔 중...")
        self.cancel_flag = False

        # tkinter 변수(IntVar/BlooeanVar 등)는 메인 스레드에서만 안전하게 읽을 수 있으므로
        # 워커 스레드로 넘기기 전에 순수 파이썬 값으로 미리 뽑아둔다.
        quality = self.quality.get()
        recursive = self.recursive.get()

        self.worker_thread = threading.Thread(
            target=self._run_worker,
            args=(src, dst, output_format, quality, recursive),
            daemon=True,
        ) 
        self.worker_thread.start()

    def _cancel(self):
        self.cancel_flag = True
        self.status_label.configure(text="취소 요청됨")

    # --------------------------------------------------------------------------
    # 워커 스레드 (UI 프리징 방지용)
    # --------------------------------------------------------------------------
    def _run_worker(self, src: str, dst: str, output_format: str, quality: int, recursive: bool):
        def progress_cb(i, total, file_result: FileResult):
            self.msg_queue.put(("progress", i, total, file_result))

        result = compress_folder(
            src_folder=src,
            dst_folder=dst,
            quality=quality,
            output_format=output_format,
            recursive=recursive,
            progress_cb=progress_cb,
            should_cancel=lambda: self.cancel_flag,
        )
        self.msg_queue.put(("done", result))

    def _poll_queue(self):
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                if msg[0] == "progress":
                    _, i, total, file_result = msg
                    self.progress.configure(maximum=max(total, 1), value=i)
                    self.status_label.configure(text=f"{i}/{total} 처리 중")
                    self._add_row(file_result)
                elif msg[0] == "done":
                    self._on_done(msg[1])
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    #---------------------------------------------------------------------------
    # 결과 표시
    # --------------------------------------------------------------------------
    def _add_row(self, fr: FileResult):
        name = os.path.basename(fr.src_path)
        if fr.status == "OK":
            self.tree.insert(
                "",
                "end",
                values=(
                    name,
                    format_bytes(fr.original_size),
                    format_bytes(fr.compressed_size),
                    f"{fr.saved_percent:.1f}%",
                    "완료",
                ),
            )
        else:
            self.tree.insert(
                "",
                "end",
                values=(name, format_bytes(fr.original_size), "-", "-", f"오류: {fr.message[:40]}"),
            )

    def _on_done(self, result: BatchResult):
        self.run_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")

        ok_count = sum(1 for f in result.files if f.status == "OK")
        err_count = sum(1 for f in result.files if f.status == "ERROR")
        self.status_label.configure(text="취소됨" if self.cancel_flag else "완료")

        self.summary_label.configure(
            text=(
                f"총 {len(result.files)}개 파일 (성공 {ok_count}, 오류 {err_count})  |  "
                f"원본 총 용량 {format_bytes(result.total_original)} -> "
                f"압축 후 {format_bytes(result.total_compressed)} | "
                f"절감 {format_bytes(result.total_saved)} ({result.total_saved_percent:.1f}%)"
            )
        )

        if not self.cancel_flag and len(result.files) > 0:
            if err_count == 0:
                messagebox.showinfo("완료", "이미지 압축이 완료되었습니다.")
            else:
                messagebox.showwarning("완료 (일부 오류)", f"{err_count}개 파일에서 오류가 발생했습니다.")
        elif len(result.files) == 0 and not self.cancel_flag:
            messagebox.showinfo("알림", "폴더에서 처리할 이미지를 찾지 못했습니다.")


def main():
    root = tk.Tk()
    try:
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
    except Exception:
        pass
    ImageCompressorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
