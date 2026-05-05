import io
import os
import json
import base64
import html as html_mod
import shutil
import subprocess
import sys
import tempfile
import re
import threading
import traceback

import customtkinter as ctk
from tkinter import filedialog, messagebox
import cv2
from scenedetect import open_video, SceneManager
from scenedetect.detectors import ContentDetector
import whisper

try:
    import ollama as _ollama_lib
    OLLAMA_AVAILABLE = True
except ImportError:
    _ollama_lib = None
    OLLAMA_AVAILABLE = False


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

WHISPER_MODELS = {
    "tiny   — быстро, менее точно": "tiny",
    "base   — баланс скорости и качества": "base",
    "small  — хорошее качество": "small",
    "medium — высокое качество": "medium",
    "large  — лучшее качество, медленно": "large",
}

FALLBACK_INTERVAL_SEC = 30
TEXT_INTERVAL_SEC = 10  # группировать текст каждые N секунд


def _sensitivity_to_threshold(s: float) -> float:
    return round(32.0 / s, 1)


def _fmt_label(sec: float) -> str:
    """00 01 30 — формат метки для текста и имён файлов."""
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    return f"{h:02d} {m:02d} {s:02d}"


def _fmt_filename(sec: float) -> str:
    """00_01_30.jpg — имя файла скриншота."""
    return _fmt_label(sec).replace(" ", "_") + ".jpg"


def _group_segments(segments: list, interval: int = TEXT_INTERVAL_SEC) -> list:
    """Группирует сегменты Whisper по N-секундным интервалам.
    Возвращает [{"time_sec": float, "label": str, "text": str}, ...]
    """
    if not segments:
        return []
    buckets: dict[int, list] = {}
    for seg in segments:
        bucket = int(seg["start"] // interval) * interval
        buckets.setdefault(bucket, []).append(seg["text"].strip())
    return [
        {"time_sec": float(t), "label": _fmt_label(float(t)), "text": " ".join(texts)}
        for t, texts in sorted(buckets.items())
    ]



def _generate_html(out_dir: str, video_name: str, chunks: list, screenshots: list,
                   summary: str = None, keypoints: list = None) -> str:
    events = []
    for c in chunks:
        events.append({"t": c["time_sec"], "type": "text", "data": c})
    for s in screenshots:
        events.append({"t": s["time_sec"], "type": "shot", "data": s})
    events.sort(key=lambda e: e["t"])

    parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        f"<title>{html_mod.escape(video_name)}</title>",
        "<style>",
        "body{font-family:Arial,sans-serif;max-width:820px;margin:40px auto;background:#fff;color:#111;line-height:1.6;}",
        "h1{font-size:22px;margin-bottom:24px;}",
        "img{max-width:100%;display:block;margin:16px auto;border:1px solid #ddd;}",
        ".lbl{text-align:center;font-size:11px;font-weight:bold;color:#555;margin:4px 0 20px;}",
        ".row{margin:6px 0;} .ts{font-weight:bold;}",
        ".meta{background:#f4f7fb;border-left:4px solid #2d7dd2;padding:14px 18px;margin:0 0 20px;border-radius:0 6px 6px 0;}",
        ".meta h2{font-size:14px;font-weight:bold;color:#2d7dd2;margin:0 0 8px;}",
        ".meta p{margin:0;} .meta ol{margin:4px 0;padding-left:20px;} .meta li{margin:3px 0;}",
        "</style></head><body>",
        f"<h1>{html_mod.escape(video_name)}</h1>",
    ]

    if summary:
        parts.append('<div class="meta">')
        parts.append('<h2>Краткое содержание</h2>')
        parts.append(f'<p>{html_mod.escape(summary)}</p>')
        parts.append('</div>')

    if keypoints:
        parts.append('<div class="meta">')
        parts.append('<h2>Ключевые моменты</h2><ol>')
        for kp in keypoints:
            parts.append(
                f'<li><span class="ts">{html_mod.escape(kp["label"])}</span>'
                f' — {html_mod.escape(kp["text"])}</li>'
            )
        parts.append('</ol></div>')

    if summary or keypoints:
        parts.append('<hr style="margin:24px 0;border:none;border-top:1px solid #ddd;">')

    for ev in events:
        if ev["type"] == "shot":
            shot = ev["data"]
            img_path = os.path.join(out_dir, shot["filename"])
            if os.path.exists(img_path):
                img = cv2.imread(img_path)
                if img is not None:
                    h, w = img.shape[:2]
                    if w > 960:
                        img = cv2.resize(img, (960, int(h * 960 / w)))
                    _, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 75])
                    b64 = base64.b64encode(buf.tobytes()).decode('ascii')
                    parts.append(f'<img src="data:image/jpeg;base64,{b64}" alt="{html_mod.escape(shot["label"])}">')
            parts.append(f'<div class="lbl">{html_mod.escape(shot["label"])}</div>')
        else:
            chunk = ev["data"]
            parts.append(
                f'<p class="row"><span class="ts">{html_mod.escape(chunk["label"])}:</span> '
                f'{html_mod.escape(chunk["text"])}</p>'
            )

    parts.append("</body></html>")

    html_path = os.path.join(out_dir, "index.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    return html_path


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Транскрибатор 2")
        self.geometry("700x720")
        self.resizable(False, False)
        self.video_path = None
        self._build_ui()

    def _build_ui(self):
        ctk.CTkLabel(self, text="Транскрибатор 2", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(20, 5))
        ctk.CTkLabel(self, text="Транскрибация • Скриншоты • HTML-документ",
                     font=ctk.CTkFont(size=12), text_color="gray").pack(pady=(0, 8))

        file_frame = ctk.CTkFrame(self)
        file_frame.pack(fill="x", padx=20, pady=4)
        ctk.CTkButton(file_frame, text="Выбрать видео", width=140, command=self.select_video).pack(side="left", padx=10, pady=10)
        self.path_label = ctk.CTkLabel(file_frame, text="Файл не выбран", anchor="w", width=480)
        self.path_label.pack(side="left", padx=5)

        model_frame = ctk.CTkFrame(self)
        model_frame.pack(fill="x", padx=20, pady=4)
        ctk.CTkLabel(model_frame, text="Модель Whisper:", width=140).pack(side="left", padx=10, pady=10)
        self.model_var = ctk.StringVar(value=list(WHISPER_MODELS.keys())[1])
        ctk.CTkOptionMenu(model_frame, variable=self.model_var, values=list(WHISPER_MODELS.keys()), width=360).pack(side="left", padx=5)

        text_frame = ctk.CTkFrame(self)
        text_frame.pack(fill="x", padx=20, pady=4)
        ctk.CTkLabel(text_frame, text="Текст каждые:", width=140).pack(side="left", padx=10, pady=10)
        ctk.CTkLabel(text_frame, text="0 с").pack(side="left")
        self.text_slider = ctk.CTkSlider(text_frame, from_=0, to=30, number_of_steps=6, width=260,
                                         command=self._on_text_slider)
        self.text_slider.set(10)
        self.text_slider.pack(side="left", padx=8)
        ctk.CTkLabel(text_frame, text="30 с").pack(side="left")
        self.text_label = ctk.CTkLabel(text_frame, text="10 сек", width=60, text_color="gray")
        self.text_label.pack(side="left", padx=8)

        sens_frame = ctk.CTkFrame(self)
        sens_frame.pack(fill="x", padx=20, pady=4)
        ctk.CTkLabel(sens_frame, text="Скриншотов:", width=140).pack(side="left", padx=10, pady=10)
        ctk.CTkLabel(sens_frame, text="мало").pack(side="left")
        self.sens_slider = ctk.CTkSlider(sens_frame, from_=1, to=10, number_of_steps=9, width=260,
                                         command=self._on_slider)
        self.sens_slider.set(5)
        self.sens_slider.pack(side="left", padx=8)
        ctk.CTkLabel(sens_frame, text="много").pack(side="left")
        self.sens_label = ctk.CTkLabel(sens_frame, text=f"порог: {_sensitivity_to_threshold(5)}", width=90,
                                       text_color="gray")
        self.sens_label.pack(side="left", padx=8)

        toggle_frame = ctk.CTkFrame(self)
        toggle_frame.pack(fill="x", padx=20, pady=4)
        self.screenshots_switch = ctk.CTkSwitch(
            toggle_frame, text="Скриншоты", width=140,
            command=self._on_screenshots_toggle)
        self.screenshots_switch.select()
        self.screenshots_switch.pack(side="left", padx=20, pady=10)
        self.html_switch = ctk.CTkSwitch(toggle_frame, text="HTML-отчёт")
        self.html_switch.select()
        self.html_switch.pack(side="left", padx=20, pady=10)
        self.ollama_switch = ctk.CTkSwitch(toggle_frame, text="Улучшить текст (Ollama)",
                                           command=self._on_ollama_toggle)
        self.ollama_switch.pack(side="left", padx=20, pady=10)

        ollama_frame = ctk.CTkFrame(self)
        ollama_frame.pack(fill="x", padx=20, pady=4)
        ctk.CTkLabel(ollama_frame, text="Модель Ollama:", width=140).pack(side="left", padx=10, pady=8)
        self.ollama_model_entry = ctk.CTkEntry(ollama_frame, width=180, placeholder_text="gemma3:12b")
        self.ollama_model_entry.insert(0, "gemma3:12b")
        self.ollama_model_entry.configure(state="disabled")
        self.ollama_model_entry.pack(side="left", padx=5)
        if not OLLAMA_AVAILABLE:
            ctk.CTkLabel(ollama_frame, text="⚠ pip install ollama",
                         text_color="orange", font=ctk.CTkFont(size=11)).pack(side="left", padx=10)

        ollama_opts_frame = ctk.CTkFrame(self)
        ollama_opts_frame.pack(fill="x", padx=20, pady=4)
        self.summary_switch = ctk.CTkSwitch(ollama_opts_frame, text="Краткое содержание",
                                            state="disabled")
        self.summary_switch.pack(side="left", padx=20, pady=8)
        self.keypoints_switch = ctk.CTkSwitch(ollama_opts_frame, text="Ключевые моменты",
                                              state="disabled")
        self.keypoints_switch.pack(side="left", padx=20, pady=8)

        self.process_btn = ctk.CTkButton(self, text="Обработать", height=40,
                                         font=ctk.CTkFont(size=15, weight="bold"),
                                         command=self.start_processing, state="disabled")
        self.process_btn.pack(padx=20, pady=10)

        self.progress = ctk.CTkProgressBar(self, width=660)
        self.progress.pack(padx=20, pady=(0, 4))
        self.progress.set(0)

        self.status_label = ctk.CTkLabel(self, text="", text_color="gray")
        self.status_label.pack(padx=20, pady=2)

        self.log_box = ctk.CTkTextbox(self, height=200, font=ctk.CTkFont(family="Courier New", size=12))
        self.log_box.pack(fill="both", expand=True, padx=20, pady=(4, 20))

    def _on_text_slider(self, value):
        v = int(round(value / 5) * 5)
        self.text_label.configure(text="сегменты" if v == 0 else f"{v} сек")

    def _on_slider(self, value):
        self.sens_label.configure(text=f"порог: {_sensitivity_to_threshold(float(value))}")

    def _on_screenshots_toggle(self):
        state = "normal" if self.screenshots_switch.get() else "disabled"
        self.sens_slider.configure(state=state)

    def _on_ollama_toggle(self):
        state = "normal" if self.ollama_switch.get() else "disabled"
        self.ollama_model_entry.configure(state=state)
        self.summary_switch.configure(state=state)
        self.keypoints_switch.configure(state=state)

    def select_video(self):
        path = filedialog.askopenfilename(
            title="Выберите видео",
            filetypes=[("Видео файлы", "*.mp4 *.mkv *.avi *.mov *.webm"), ("Все файлы", "*.*")]
        )
        if path:
            self.video_path = path
            self.path_label.configure(text=os.path.basename(path))
            self.process_btn.configure(state="normal")

    def start_processing(self):
        self.process_btn.configure(state="disabled")
        self.log_box.delete("1.0", "end")
        self.progress.set(0)
        self.status_label.configure(text="")
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        try:
            video_path = self.video_path
            do_screenshots = bool(self.screenshots_switch.get())
            do_html = bool(self.html_switch.get())
            do_ollama = bool(self.ollama_switch.get())
            do_summary = bool(self.summary_switch.get())
            do_keypoints = bool(self.keypoints_switch.get())
            ollama_model = self.ollama_model_entry.get().strip() or "gemma3:12b"
            text_interval = int(round(self.text_slider.get() / 5) * 5)

            video_name = os.path.splitext(os.path.basename(video_path))[0].strip()
            out_dir = os.path.join(os.path.dirname(video_path), video_name + "_v2")
            os.makedirs(out_dir, exist_ok=True)

            # ── Шаг 1: транскрибация ─────────────────────────────────────
            self._ui(lambda: self.status_label.configure(text="Транскрибация..."))
            model_name = WHISPER_MODELS[self.model_var.get()]
            self._log(f"Загрузка модели Whisper «{model_name}»...")
            self._log("  (первая загрузка скачивает файл — подождите...)")
            # pythonw.exe не имеет консоли: sys.stdout/stderr = None,
            # из-за этого tqdm падает при скачивании модели.
            # Подставляем заглушку на время загрузки.
            _stdout, _stderr = sys.stdout, sys.stderr
            if sys.stdout is None:
                sys.stdout = io.StringIO()
            if sys.stderr is None:
                sys.stderr = io.StringIO()
            try:
                model = whisper.load_model(model_name)
            finally:
                sys.stdout, sys.stderr = _stdout, _stderr

            self._log("Транскрибация видео...")
            result = model.transcribe(video_path, verbose=None, fp16=False)

            segments = [
                {"start": round(s["start"], 2), "end": round(s["end"], 2), "text": s["text"]}
                for s in result.get("segments", [])
            ]

            if text_interval == 0:
                chunks = [
                    {"time_sec": s["start"], "label": _fmt_label(s["start"]), "text": s["text"].strip()}
                    for s in segments if s["text"].strip()
                ]
            else:
                chunks = _group_segments(segments, text_interval)

            txt_path = os.path.join(out_dir, f"{video_name}.txt")
            with open(txt_path, "w", encoding="utf-8") as f:
                for chunk in chunks:
                    f.write(f"{chunk['label']}: {chunk['text']}\n\n")
            self._log(f"✓ Транскрипция сохранена: {os.path.basename(txt_path)}")
            interval_label = "сегменты" if text_interval == 0 else f"{text_interval} сек"
            self._log(f"  Блоков ({interval_label}): {len(chunks)}")
            self._ui(lambda: self.progress.set(0.35))

            # ── Шаг 1б: улучшение текста через Ollama ────────────────────
            summary = None
            keypoints = None
            if do_ollama or do_summary or do_keypoints:
                if not OLLAMA_AVAILABLE:
                    self._log("⚠ Ollama: библиотека не установлена — pip install ollama")
                else:
                    if do_ollama:
                        self._ui(lambda: self.status_label.configure(text="Улучшение текста (Ollama)..."))
                        self._log(f"Улучшение текста через Ollama ({ollama_model})...")
                        try:
                            chunks = self._improve_text_ollama(chunks, ollama_model)
                            with open(txt_path, "w", encoding="utf-8") as f:
                                for chunk in chunks:
                                    f.write(f"{chunk['label']}: {chunk['text']}\n\n")
                            self._log("✓ Текст улучшен и перезаписан")
                        except Exception as e:
                            self._log(f"⚠ Ollama (улучшение): {e}")
                    if do_summary:
                        self._ui(lambda: self.status_label.configure(text="Краткое содержание (Ollama)..."))
                        self._log(f"Краткое содержание через Ollama ({ollama_model})...")
                        try:
                            summary = self._summarize_with_ollama(chunks, ollama_model)
                            self._log("✓ Краткое содержание готово")
                        except Exception as e:
                            self._log(f"⚠ Ollama (содержание): {e}")
                    if do_keypoints:
                        self._ui(lambda: self.status_label.configure(text="Ключевые моменты (Ollama)..."))
                        self._log(f"Ключевые моменты через Ollama ({ollama_model})...")
                        try:
                            keypoints = self._keypoints_with_ollama(chunks, ollama_model)
                            self._log(f"✓ Ключевых моментов: {len(keypoints)}")
                        except Exception as e:
                            self._log(f"⚠ Ollama (моменты): {e}")
            self._ui(lambda: self.progress.set(0.4))

            # ── Шаг 2: скриншоты ─────────────────────────────────────────
            screenshots = []
            if do_screenshots:
                self._ui(lambda: self.status_label.configure(text="Скриншоты..."))
                threshold = _sensitivity_to_threshold(self.sens_slider.get())
                self._log(f"Анализ смены кадров (порог {threshold})...")

                cap = cv2.VideoCapture(video_path)
                fps = cap.get(cv2.CAP_PROP_FPS) or 25
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

                scene_frames = self._detect_scenes(video_path, threshold)
                if not scene_frames:
                    self._log(f"Сцены не найдены — скриншот каждые {FALLBACK_INTERVAL_SEC} с.")
                    interval = int(fps * FALLBACK_INTERVAL_SEC)
                    scene_frames = list(range(0, total_frames, interval))

                self._log(f"Найдено сцен: {len(scene_frames)}")

                for i, frame_num in enumerate(scene_frames, 1):
                    time_sec = frame_num / fps
                    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
                    ret, frame = cap.read()
                    if ret:
                        filename = _fmt_filename(time_sec)
                        cv2.imwrite(os.path.join(out_dir, filename), frame)
                        screenshots.append({
                            "time_sec": round(time_sec, 2),
                            "label": _fmt_label(time_sec),
                            "filename": filename,
                        })
                    self._ui(lambda p=0.4 + 0.3 * (i / len(scene_frames)): self.progress.set(p))

                cap.release()
                self._log(f"✓ Скриншотов сохранено: {len(screenshots)}")
            else:
                self._log("Скриншоты отключены — пропущено.")
            self._ui(lambda: self.progress.set(0.7))

            # ── Шаг 3: HTML-документ ─────────────────────────────────────
            html_path = None
            if do_html:
                self._ui(lambda: self.status_label.configure(text="HTML-документ..."))
                self._log("Генерация HTML-документа...")
                html_path = _generate_html(out_dir, video_name, chunks, screenshots,
                                           summary=summary, keypoints=keypoints)
                self._log(f"✓ HTML сохранён: {os.path.basename(html_path)}")
            else:
                self._log("HTML-отчёт отключён — пропущено.")

            self._ui(lambda: self.progress.set(1.0))
            self._ui(lambda: self.status_label.configure(text="Готово!", text_color="green"))

            # Открываем папку в Explorer
            subprocess.Popen(['explorer', os.path.normpath(out_dir)])

            # Открываем HTML если сгенерирован
            if html_path:
                temp_html = os.path.join(tempfile.gettempdir(), "trunscribator.html")
                shutil.copy2(html_path, temp_html)
                os.startfile(temp_html)

            result_lines = (
                f"Транскрипция: {os.path.basename(txt_path)}\n"
                f"Скриншотов: {len(screenshots)}\n"
                + (f"HTML-документ: {os.path.basename(html_path)}\n" if html_path else "")
                + f"\nПапка с результатами:\n{out_dir}"
            )
            self._ui(lambda: messagebox.showinfo("Готово", f"Обработка завершена!\n\n{result_lines}"))

        except Exception as e:
            self._log(f"ОШИБКА: {e}")
            self._log(traceback.format_exc())
            self._ui(lambda: self.status_label.configure(text="Ошибка", text_color="red"))
        finally:
            self._ui(lambda: self.process_btn.configure(state="normal"))

    def _improve_text_ollama(self, chunks: list, model: str) -> list:
        if not chunks:
            return chunks
        numbered = "\n".join(f"{i + 1}. {c['text']}" for i, c in enumerate(chunks))
        prompt = (
            "Исправь ошибки автоматического распознавания речи в каждой строке.\n"
            "Верни ответ строго в том же формате — нумерованный список с теми же номерами.\n"
            "Не добавляй и не убирай строки. Верни только список, без пояснений.\n\n"
            + numbered
        )
        response = _ollama_lib.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        corrected = response["message"]["content"].strip()
        result = [dict(c) for c in chunks]
        for line in corrected.split("\n"):
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^(\d+)[.)]\s+(.*)", line)
            if m:
                idx = int(m.group(1)) - 1
                if 0 <= idx < len(result):
                    result[idx]["text"] = m.group(2).strip()
        return result

    def _summarize_with_ollama(self, chunks: list, model: str) -> str:
        full_text = "\n".join(f"{c['label']}: {c['text']}" for c in chunks)
        prompt = (
            "Ты получаешь транскрипцию видео. Напиши краткое содержание в 3–5 предложениях "
            "на русском языке. Верни только само содержание, без вводных слов и пояснений.\n\n"
            + full_text
        )
        response = _ollama_lib.chat(model=model, messages=[{"role": "user", "content": prompt}])
        return response["message"]["content"].strip()

    def _keypoints_with_ollama(self, chunks: list, model: str) -> list:
        full_text = "\n".join(f"{c['label']}: {c['text']}" for c in chunks)
        prompt = (
            "Ты получаешь транскрипцию видео с временными метками (формат ЧЧ ММ СС).\n"
            "Выдели 5–10 ключевых моментов. Для каждого укажи временную метку из текста "
            "и краткое описание (до 10 слов).\n"
            "Формат — строго нумерованный список:\n"
            "1. ЧЧ ММ СС — описание\n"
            "2. ЧЧ ММ СС — описание\n"
            "Только список, без вводных слов и пояснений.\n\n"
            + full_text
        )
        response = _ollama_lib.chat(model=model, messages=[{"role": "user", "content": prompt}])
        result = []
        for line in response["message"]["content"].strip().split("\n"):
            line = line.strip()
            m = re.match(r"^\d+[.)]\s+(\d{2}\s\d{2}\s\d{2})\s*[—\-]\s*(.+)", line)
            if m:
                result.append({"label": m.group(1), "text": m.group(2).strip()})
        return result

    def _detect_scenes(self, video_path: str, threshold: float) -> list[int]:
        video = open_video(video_path)
        scene_manager = SceneManager()
        scene_manager.add_detector(ContentDetector(threshold=threshold))
        scene_manager.detect_scenes(video, show_progress=False)
        return [s[0].get_frames() for s in scene_manager.get_scene_list()]

    def _log(self, msg: str):
        self.after(0, lambda m=msg: (self.log_box.insert("end", m + "\n"), self.log_box.see("end")))

    def _ui(self, fn):
        self.after(0, fn)


if __name__ == "__main__":
    app = App()
    app.mainloop()
