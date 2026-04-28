import os
import threading
import subprocess
import sys

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

FALLBACK_INTERVAL_SEC = 30  # если сцен не найдено — скриншот каждые N секунд


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Транскрибатор")
        self.geometry("700x560")
        self.resizable(False, False)
        self.video_path = None
        self._build_ui()

    # ── UI ──────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Заголовок
        ctk.CTkLabel(self, text="Транскрибатор видео", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(20, 5))

        # Выбор файла
        file_frame = ctk.CTkFrame(self)
        file_frame.pack(fill="x", padx=20, pady=8)
        ctk.CTkButton(file_frame, text="Выбрать видео", width=140, command=self.select_video).pack(side="left", padx=10, pady=10)
        self.path_label = ctk.CTkLabel(file_frame, text="Файл не выбран", anchor="w", width=480)
        self.path_label.pack(side="left", padx=5)

        # Выбор модели
        model_frame = ctk.CTkFrame(self)
        model_frame.pack(fill="x", padx=20, pady=4)
        ctk.CTkLabel(model_frame, text="Модель Whisper:", width=140).pack(side="left", padx=10, pady=10)
        self.model_var = ctk.StringVar(value=list(WHISPER_MODELS.keys())[1])
        ctk.CTkOptionMenu(model_frame, variable=self.model_var, values=list(WHISPER_MODELS.keys()), width=360).pack(side="left", padx=5)

        # Кнопка обработки
        self.process_btn = ctk.CTkButton(self, text="Обработать", height=40, font=ctk.CTkFont(size=15, weight="bold"),
                                         command=self.start_processing, state="disabled")
        self.process_btn.pack(padx=20, pady=10)

        # Прогресс-бар
        self.progress = ctk.CTkProgressBar(self, width=660)
        self.progress.pack(padx=20, pady=(0, 4))
        self.progress.set(0)

        # Статус
        self.status_label = ctk.CTkLabel(self, text="", text_color="gray")
        self.status_label.pack(padx=20, pady=2)

        # Лог
        self.log_box = ctk.CTkTextbox(self, height=220, font=ctk.CTkFont(family="Courier New", size=12))
        self.log_box.pack(fill="both", expand=True, padx=20, pady=(4, 20))

    # ── Действия ────────────────────────────────────────────────────────────

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

    # ── Воркер (фоновый поток) ───────────────────────────────────────────

    def _worker(self):
        try:
            video_path = self.video_path
            video_name = os.path.splitext(os.path.basename(video_path))[0]
            out_dir = os.path.join(os.path.dirname(video_path), video_name)
            os.makedirs(out_dir, exist_ok=True)

            # ── Шаг 1: транскрибация ────────────────────────────────────
            self._ui(lambda: self.status_label.configure(text="Шаг 1/2 — Транскрибация..."))
            model_key = self.model_var.get()
            model_name = WHISPER_MODELS[model_key]
            self._log(f"Загрузка модели Whisper «{model_name}»...")
            model = whisper.load_model(model_name)
            self._log("Транскрибация видео (может занять несколько минут)...")
            result = model.transcribe(video_path, verbose=False)

            txt_path = os.path.join(out_dir, f"{video_name}.txt")
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(result["text"].strip())
            self._log(f"✓ Транскрипция сохранена: {os.path.basename(txt_path)}")
            self._ui(lambda: self.progress.set(0.5))

            # ── Шаг 2: скриншоты по сценам ──────────────────────────────
            self._ui(lambda: self.status_label.configure(text="Шаг 2/2 — Определение сцен..."))
            self._log("Анализ смены кадров...")

            cap = cv2.VideoCapture(video_path)
            fps = cap.get(cv2.CAP_PROP_FPS) or 25
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

            # Определяем сцены
            scene_frames = self._detect_scenes(video_path)

            if not scene_frames:
                # Запасной вариант: каждые FALLBACK_INTERVAL_SEC секунд
                self._log(f"Сцены не найдены — делаем скриншот каждые {FALLBACK_INTERVAL_SEC} с.")
                interval = int(fps * FALLBACK_INTERVAL_SEC)
                scene_frames = list(range(0, total_frames, interval))

            self._log(f"Найдено сцен: {len(scene_frames)}")

            for i, frame_num in enumerate(scene_frames, 1):
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
                ret, frame = cap.read()
                if ret:
                    img_path = os.path.join(out_dir, f"{i}.jpg")
                    cv2.imwrite(img_path, frame)
                progress = 0.5 + 0.5 * (i / len(scene_frames))
                self._ui(lambda p=progress: self.progress.set(p))

            cap.release()
            self._log(f"✓ Скриншоты сохранены в папку: {out_dir}")

            # ── Готово ──────────────────────────────────────────────────
            self._ui(lambda: self.progress.set(1.0))
            self._ui(lambda: self.status_label.configure(text="Готово!", text_color="green"))
            self._ui(lambda: messagebox.showinfo(
                "Готово",
                f"Обработка завершена!\n\n"
                f"Транскрипция: {os.path.basename(txt_path)}\n"
                f"Скриншотов: {len(scene_frames)}\n\n"
                f"Папка с результатами:\n{out_dir}"
            ))

        except Exception as e:
            self._log(f"ОШИБКА: {e}")
            self._ui(lambda: self.status_label.configure(text="Ошибка", text_color="red"))
        finally:
            self._ui(lambda: self.process_btn.configure(state="normal"))

    def _detect_scenes(self, video_path: str) -> list[int]:
        """Возвращает список номеров кадров начала каждой сцены."""
        video = open_video(video_path)
        scene_manager = SceneManager()
        scene_manager.add_detector(ContentDetector(threshold=27.0))
        scene_manager.detect_scenes(video, show_progress=False)
        scene_list = scene_manager.get_scene_list()
        return [scene[0].get_frames() for scene in scene_list]

    # ── Хелперы ─────────────────────────────────────────────────────────────

    def _log(self, msg: str):
        self.after(0, lambda m=msg: (self.log_box.insert("end", m + "\n"), self.log_box.see("end")))

    def _ui(self, fn):
        self.after(0, fn)


if __name__ == "__main__":
    app = App()
    app.mainloop()
