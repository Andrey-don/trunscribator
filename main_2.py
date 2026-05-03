import os
import json
import base64
import html as html_mod
import shutil
import subprocess
import tempfile
import threading

import customtkinter as ctk
from tkinter import filedialog, messagebox
import cv2
from scenedetect import open_video, SceneManager
from scenedetect.detectors import ContentDetector
import whisper


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



def _generate_html(out_dir: str, video_name: str, chunks: list, screenshots: list) -> str:
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
        "</style></head><body>",
        f"<h1>{html_mod.escape(video_name)}</h1>",
    ]

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
        self.geometry("700x620")
        self.resizable(False, False)
        self.video_path = None
        self._build_ui()

    def _build_ui(self):
        ctk.CTkLabel(self, text="Транскрибатор 2", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(20, 5))
        ctk.CTkLabel(self, text="Тайминг каждые 10 сек • Скриншоты по времени • HTML-документ",
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

    def _on_slider(self, value):
        self.sens_label.configure(text=f"порог: {_sensitivity_to_threshold(float(value))}")

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
            video_name = os.path.splitext(os.path.basename(video_path))[0].strip()
            out_dir = os.path.join(os.path.dirname(video_path), video_name + "_v2")
            os.makedirs(out_dir, exist_ok=True)

            # ── Шаг 1: транскрибация ─────────────────────────────────────
            self._ui(lambda: self.status_label.configure(text="Шаг 1/3 — Транскрибация..."))
            model_name = WHISPER_MODELS[self.model_var.get()]
            self._log(f"Загрузка модели Whisper «{model_name}»...")
            model = whisper.load_model(model_name)
            self._log("Транскрибация видео...")
            result = model.transcribe(video_path, verbose=None)

            segments = [
                {"start": round(s["start"], 2), "end": round(s["end"], 2), "text": s["text"]}
                for s in result.get("segments", [])
            ]

            # Группируем по 10-сек интервалам
            chunks = _group_segments(segments, TEXT_INTERVAL_SEC)

            # Сохраняем текст с таймингами
            txt_path = os.path.join(out_dir, f"{video_name}.txt")
            with open(txt_path, "w", encoding="utf-8") as f:
                for chunk in chunks:
                    f.write(f"{chunk['label']}: {chunk['text']}\n\n")
            self._log(f"✓ Транскрипция сохранена: {os.path.basename(txt_path)}")
            self._log(f"  Блоков по {TEXT_INTERVAL_SEC} сек: {len(chunks)}")
            self._ui(lambda: self.progress.set(0.4))

            # ── Шаг 2: скриншоты ─────────────────────────────────────────
            self._ui(lambda: self.status_label.configure(text="Шаг 2/3 — Скриншоты..."))
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

            screenshots = []
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

            # Сохраняем манифест
            manifest = {"video": os.path.basename(video_path), "chunks": chunks, "screenshots": screenshots}
            with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
            self._ui(lambda: self.progress.set(0.7))

            # ── Шаг 3: HTML-документ ─────────────────────────────────────
            self._ui(lambda: self.status_label.configure(text="Шаг 3/3 — HTML-документ..."))
            self._log("Генерация HTML-документа...")
            html_path = _generate_html(out_dir, video_name, chunks, screenshots)
            self._log(f"✓ HTML сохранён: {os.path.basename(html_path)}")

            self._ui(lambda: self.progress.set(1.0))
            self._ui(lambda: self.status_label.configure(text="Готово!", text_color="green"))

            # Открываем папку в Explorer
            subprocess.Popen(['explorer', os.path.normpath(out_dir)])

            # Копируем HTML во временную папку с коротким ASCII-путём и открываем
            temp_html = os.path.join(tempfile.gettempdir(), "trunscribator.html")
            shutil.copy2(html_path, temp_html)
            os.startfile(temp_html)

            self._ui(lambda: messagebox.showinfo(
                "Готово",
                f"Обработка завершена!\n\n"
                f"Транскрипция: {os.path.basename(txt_path)}\n"
                f"Скриншотов: {len(screenshots)}\n"
                f"HTML-документ: {os.path.basename(html_path)}\n\n"
                f"Папка с результатами:\n{out_dir}"
            ))

        except Exception as e:
            self._log(f"ОШИБКА: {e}")
            self._ui(lambda: self.status_label.configure(text="Ошибка", text_color="red"))
        finally:
            self._ui(lambda: self.process_btn.configure(state="normal"))

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
