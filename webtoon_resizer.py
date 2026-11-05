import os
import sys
import threading
import time
import re
from PIL import Image
import customtkinter as ctk
from tkinter import filedialog, messagebox

# Try importing windnd for drag & drop
try:
    import windnd
    HAS_WINDND = True
except ImportError:
    HAS_WINDND = False

# Set appearance and theme
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

def natural_sort_key(s):
    """Sort strings containing numbers in human order (1, 2, 10 instead of 1, 10, 2)."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

class WebtoonResizerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Webtoon Raw Resizer | مُحوّل مقاسات راو الويب تون")
        self.geometry("780x740")
        self.minsize(720, 680)

        # State variables
        self.source_dir = ""
        self.output_dir = ""
        self.is_converting = False
        self.cancel_requested = False
        self.image_files = []

        self._build_ui()

        # Hook drag and drop if available
        if HAS_WINDND:
            try:
                windnd.hook_dropfiles(self, func=self.handle_drop, force_unicode=True)
            except Exception as e:
                print("windnd hook error:", e)

    def _build_ui(self):
        # Main container with padding
        self.main_frame = ctk.CTkScrollableFrame(self, corner_radius=12)
        self.main_frame.pack(fill="both", expand=True, padx=16, pady=16)

        # Header Title
        title_label = ctk.CTkLabel(
            self.main_frame,
            text="🎨 Webtoon Raw Resizer | أداة تحويل مقاسات الويب تون",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title_label.pack(pady=(5, 2))

        subtitle_label = ctk.CTkLabel(
            self.main_frame,
            text="تحويل صور السكرين شوت (1080p) إلى مقاس الراو الرسمي (690px) بجودة أصلية فائقة",
            font=ctk.CTkFont(size=13),
            text_color="gray70"
        )
        subtitle_label.pack(pady=(0, 12))

        # 1. Drop Zone / Folder Picker Card
        self.drop_frame = ctk.CTkFrame(self.main_frame, corner_radius=12, fg_color=("gray85", "gray17"), border_width=2, border_color=("gray70", "gray30"))
        self.drop_frame.pack(fill="x", padx=10, pady=8)

        drop_icon_label = ctk.CTkLabel(
            self.drop_frame,
            text="📁",
            font=ctk.CTkFont(size=36)
        )
        drop_icon_label.pack(pady=(12, 2))

        drop_text = "اسحب وأفلت مجلد الصور هنا (Drag & Drop Folder Here)" if HAS_WINDND else "اختر مجلد صور الفصل للبدء"
        self.drop_label = ctk.CTkLabel(
            self.drop_frame,
            text=drop_text,
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.drop_label.pack(pady=2)

        browse_btn = ctk.CTkButton(
            self.drop_frame,
            text="تصفح لاختيار المجلد... (Browse Folder)",
            command=self.browse_source_folder,
            font=ctk.CTkFont(size=13, weight="bold"),
            height=36,
            corner_radius=8
        )
        browse_btn.pack(pady=(8, 12))

        # Selected Folder Info
        self.folder_info_label = ctk.CTkLabel(
            self.drop_frame,
            text="لم يتم اختيار أي مجلد حتى الآن",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray65"),
            wraplength=650
        )
        self.folder_info_label.pack(pady=(0, 10))

        # 2. Settings Section
        settings_frame = ctk.CTkFrame(self.main_frame, corner_radius=12)
        settings_frame.pack(fill="x", padx=10, pady=8)

        settings_title = ctk.CTkLabel(
            settings_frame,
            text="⚙️ إعدادات التحويل (Conversion Settings)",
            font=ctk.CTkFont(size=15, weight="bold")
        )
        settings_title.pack(anchor="w", padx=16, pady=(12, 8))

        # Width Presets Row
        width_row = ctk.CTkFrame(settings_frame, fg_color="transparent")
        width_row.pack(fill="x", padx=16, pady=4)

        width_label = ctk.CTkLabel(
            width_row,
            text="العرض المستهدف (Target Width):",
            font=ctk.CTkFont(size=13, weight="bold"),
            width=200,
            anchor="w"
        )
        width_label.pack(side="left")

        self.preset_var = ctk.StringVar(value="690 px (راو Naver الرسمي)")
        self.preset_menu = ctk.CTkOptionMenu(
            width_row,
            values=[
                "690 px (راو Naver الرسمي)",
                "720 px (ستاندرد الويب تون)",
                "800 px (كاكاو / تاباس)",
                "مخصص (Custom)"
            ],
            variable=self.preset_var,
            command=self.on_preset_change,
            width=230
        )
        self.preset_menu.pack(side="left", padx=(0, 10))

        self.custom_width_entry = ctk.CTkEntry(
            width_row,
            width=80,
            placeholder_text="690"
        )
        self.custom_width_entry.insert(0, "690")
        self.custom_width_entry.pack(side="left")

        px_lbl = ctk.CTkLabel(width_row, text="px", font=ctk.CTkFont(size=12))
        px_lbl.pack(side="left", padx=4)

        # Aspect Ratio & Options Row
        options_row = ctk.CTkFrame(settings_frame, fg_color="transparent")
        options_row.pack(fill="x", padx=16, pady=6)

        self.keep_aspect_var = ctk.BooleanVar(value=True)
        self.keep_aspect_cb = ctk.CTkCheckBox(
            options_row,
            text="الحفاظ على نسبة الأبعاد تلقائياً (Aspect Ratio) لمنع مط الرسم",
            variable=self.keep_aspect_var,
            font=ctk.CTkFont(size=12)
        )
        self.keep_aspect_cb.pack(side="left")

        # Format and Quality Row
        fmt_row = ctk.CTkFrame(settings_frame, fg_color="transparent")
        fmt_row.pack(fill="x", padx=16, pady=6)

        fmt_label = ctk.CTkLabel(fmt_row, text="صيغة الإخراج (Format):", font=ctk.CTkFont(size=13), width=160, anchor="w")
        fmt_label.pack(side="left")

        self.format_var = ctk.StringVar(value="JPG")
        self.format_menu = ctk.CTkOptionMenu(
            fmt_row,
            values=["JPG", "PNG", "WEBP", "نفس الصيغة الأصلية"],
            variable=self.format_var,
            width=150
        )
        self.format_menu.pack(side="left", padx=(0, 20))

        qual_label = ctk.CTkLabel(fmt_row, text="جودة الصورة (Quality):", font=ctk.CTkFont(size=13))
        qual_label.pack(side="left", padx=(0, 8))

        self.quality_var = ctk.StringVar(value="95 (فائقة)")
        self.quality_menu = ctk.CTkOptionMenu(
            fmt_row,
            values=["100 (القصوى)", "95 (فائقة)", "90 (عالية)", "85 (متوسطة)"],
            variable=self.quality_var,
            width=120
        )
        self.quality_menu.pack(side="left")

        # Output Destination Row
        dest_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
        dest_frame.pack(fill="x", padx=16, pady=(6, 14))

        self.auto_output_var = ctk.BooleanVar(value=True)
        self.auto_output_cb = ctk.CTkCheckBox(
            dest_frame,
            text="إنشاء مجلد إخراج جديد تلقائياً بجانب الأصلي (مثل: folder [690px])",
            variable=self.auto_output_var,
            command=self.toggle_output_mode,
            font=ctk.CTkFont(size=12)
        )
        self.auto_output_cb.pack(anchor="w")

        self.custom_dest_frame = ctk.CTkFrame(dest_frame, fg_color="transparent")
        # Hidden by default

        self.custom_dest_entry = ctk.CTkEntry(self.custom_dest_frame, placeholder_text="اختر مجلد الإخراج المخصص...")
        self.custom_dest_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.custom_dest_btn = ctk.CTkButton(
            self.custom_dest_frame,
            text="تحديد...",
            width=80,
            command=self.browse_output_folder
        )
        self.custom_dest_btn.pack(side="left")

        # 3. Action & Progress Section
        action_frame = ctk.CTkFrame(self.main_frame, corner_radius=12)
        action_frame.pack(fill="x", padx=10, pady=8)

        btn_row = ctk.CTkFrame(action_frame, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=12)

        self.start_btn = ctk.CTkButton(
            btn_row,
            text="🚀 بدء التحويل (Start Conversion)",
            font=ctk.CTkFont(size=15, weight="bold"),
            height=42,
            fg_color="#1f6aa5",
            hover_color="#144d75",
            command=self.start_conversion
        )
        self.start_btn.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.open_output_btn = ctk.CTkButton(
            btn_row,
            text="📂 فتح مجلد الإخراج",
            font=ctk.CTkFont(size=13),
            height=42,
            fg_color="gray30",
            state="disabled",
            command=self.open_output_folder
        )
        self.open_output_btn.pack(side="right")

        # Progress Bar & Status
        self.progress_bar = ctk.CTkProgressBar(action_frame)
        self.progress_bar.pack(fill="x", padx=16, pady=(0, 6))
        self.progress_bar.set(0)

        self.status_label = ctk.CTkLabel(
            action_frame,
            text="جاهز لبدء التحويل",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray70")
        )
        self.status_label.pack(anchor="w", padx=16, pady=(0, 10))

        # 4. Logs Box
        log_label = ctk.CTkLabel(
            self.main_frame,
            text="سجل العمليات (Conversion Log):",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        log_label.pack(anchor="w", padx=14, pady=(6, 2))

        self.log_textbox = ctk.CTkTextbox(
            self.main_frame,
            height=130,
            font=ctk.CTkFont(family="Consolas", size=11),
            corner_radius=8
        )
        self.log_textbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.log_textbox.configure(state="disabled")

    def log(self, message):
        """Append text to the log textbox safely."""
        self.log_textbox.configure(state="normal")
        self.log_textbox.insert("end", message + "\n")
        self.log_textbox.see("end")
        self.log_textbox.configure(state="disabled")

    def on_preset_change(self, value):
        if "690" in value:
            self.custom_width_entry.delete(0, "end")
            self.custom_width_entry.insert(0, "690")
        elif "720" in value:
            self.custom_width_entry.delete(0, "end")
            self.custom_width_entry.insert(0, "720")
        elif "800" in value:
            self.custom_width_entry.delete(0, "end")
            self.custom_width_entry.insert(0, "800")

    def toggle_output_mode(self):
        if self.auto_output_var.get():
            self.custom_dest_frame.pack_forget()
        else:
            self.custom_dest_frame.pack(fill="x", pady=(6, 0))

    def handle_drop(self, files):
        if not files:
            return
        dropped_path = files[0]
        if isinstance(dropped_path, bytes):
            try:
                dropped_path = dropped_path.decode('utf-8')
            except UnicodeDecodeError:
                dropped_path = dropped_path.decode('gbk', errors='ignore')

        if os.path.isfile(dropped_path):
            folder = os.path.dirname(dropped_path)
        elif os.path.isdir(dropped_path):
            folder = dropped_path
        else:
            return

        self.set_source_folder(folder)

    def browse_source_folder(self):
        folder = filedialog.askdirectory(title="اختر مجلد صور الويب تون")
        if folder:
            self.set_source_folder(folder)

    def browse_output_folder(self):
        folder = filedialog.askdirectory(title="اختر مجلد الإخراج")
        if folder:
            self.custom_dest_entry.delete(0, "end")
            self.custom_dest_entry.insert(0, folder)

    def set_source_folder(self, folder):
        folder = os.path.normpath(folder)
        self.source_dir = folder

        # Scan for images
        supported_exts = ('.jpg', '.jpeg', '.png', '.webp', '.bmp')
        try:
            all_files = os.listdir(folder)
            self.image_files = [f for f in all_files if f.lower().endswith(supported_exts)]
            self.image_files.sort(key=natural_sort_key)
        except Exception as e:
            messagebox.showerror("خطأ", f"تعذر قراءة المجلد:\n{e}")
            return

        if not self.image_files:
            self.folder_info_label.configure(
                text=f"⚠️ {folder}\nلم يتم العثور على أي ملفات صور مدعومة في هذا المجلد!",
                text_color="#e06c75"
            )
            return

        # Sample first image size
        first_size_str = ""
        try:
            with Image.open(os.path.join(folder, self.image_files[0])) as img:
                first_size_str = f" | مقاس العينة: {img.size[0]}x{img.size[1]} بكسل"
        except Exception:
            pass

        self.folder_info_label.configure(
            text=f"📁 {folder}\nعدد الصور: {len(self.image_files)} صورة{first_size_str}",
            text_color=("gray20", "gray85")
        )

        self.log(f"تم اختيار المجلد: {folder}")
        self.log(f"تم العثور على {len(self.image_files)} صورة جاهزة للتحويل.")

    def open_output_folder(self):
        if self.output_dir and os.path.exists(self.output_dir):
            os.startfile(self.output_dir)
        else:
            messagebox.showinfo("تنبيه", "مجلد الإخراج غير متوفر أو لم يتم التحويل بعد.")

    def start_conversion(self):
        if self.is_converting:
            return

        if not self.source_dir or not os.path.exists(self.source_dir):
            messagebox.showwarning("تنبيه", "يرجى اختيار مجلد الصور أولاً!")
            return

        if not self.image_files:
            messagebox.showwarning("تنبيه", "المجلد لا يحتوي على أي صور للتحويل!")
            return

        # Parse target width
        try:
            target_width = int(self.custom_width_entry.get().strip())
            if target_width <= 50 or target_width > 10000:
                raise ValueError()
        except ValueError:
            messagebox.showerror("خطأ", "يرجى إدخال عرض صحيح (رقم بين 100 و 5000 بكسل).")
            return

        # Determine output folder
        if self.auto_output_var.get():
            folder_name = os.path.basename(self.source_dir)
            parent_dir = os.path.dirname(self.source_dir)
            self.output_dir = os.path.join(parent_dir, f"{folder_name} [{target_width}px]")
        else:
            custom_path = self.custom_dest_entry.get().strip()
            if not custom_path:
                messagebox.showerror("خطأ", "يرجى تحديد مجلد الإخراج المخصص أو تفعيل الخيار التلقائي.")
                return
            self.output_dir = custom_path

        try:
            os.makedirs(self.output_dir, exist_ok=True)
        except Exception as e:
            messagebox.showerror("خطأ", f"تعذر إنشاء مجلد الإخراج:\n{e}")
            return

        # Parse format and quality
        fmt_selection = self.format_var.get()
        qual_str = self.quality_var.get().split()[0]
        try:
            quality = int(qual_str)
        except ValueError:
            quality = 95

        keep_aspect = self.keep_aspect_var.get()

        # Start thread
        self.is_converting = True
        self.start_btn.configure(state="disabled", text="⏳ جاري التحويل...")
        self.open_output_btn.configure(state="disabled")
        self.progress_bar.set(0)

        threading.Thread(
            target=self._run_conversion_worker,
            args=(target_width, keep_aspect, fmt_selection, quality),
            daemon=True
        ).start()

    def _run_conversion_worker(self, target_width, keep_aspect, fmt_selection, quality):
        total = len(self.image_files)
        success_count = 0
        error_count = 0
        start_time = time.time()

        self.log(f"\n--- بدء التحويل: {total} صورة إلى عرض {target_width}px ---")
        self.log(f"مجلد الإخراج: {self.output_dir}")

        for idx, filename in enumerate(self.image_files, start=1):
            src_path = os.path.join(self.source_dir, filename)
            base_name, ext = os.path.splitext(filename)

            # Determine target extension
            if fmt_selection == "JPG":
                out_ext = ".jpg"
                save_format = "JPEG"
            elif fmt_selection == "PNG":
                out_ext = ".png"
                save_format = "PNG"
            elif fmt_selection == "WEBP":
                out_ext = ".webp"
                save_format = "WEBP"
            else: # Original
                out_ext = ext.lower()
                save_format = "JPEG" if out_ext in ('.jpg', '.jpeg') else "PNG" if out_ext == '.png' else "WEBP" if out_ext == '.webp' else "JPEG"

            dst_path = os.path.join(self.output_dir, base_name + out_ext)

            try:
                with Image.open(src_path) as img:
                    orig_w, orig_h = img.size

                    if keep_aspect:
                        new_w = target_width
                        new_h = int(round(orig_h * (target_width / float(orig_w))))
                    else:
                        new_w = target_width
                        new_h = orig_h

                    # Convert RGBA to RGB for JPEG
                    if save_format == "JPEG" and img.mode in ("RGBA", "LA", "P"):
                        bg = Image.new("RGB", img.size, (255, 255, 255))
                        if img.mode == "P":
                            img = img.convert("RGBA")
                        bg.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
                        img_to_resize = bg
                    elif img.mode != "RGB" and save_format == "JPEG":
                        img_to_resize = img.convert("RGB")
                    else:
                        img_to_resize = img

                    # High quality Lanczos resize
                    resized = img_to_resize.resize((new_w, new_h), Image.Resampling.LANCZOS)

                    # Save with parameters
                    if save_format in ("JPEG", "WEBP"):
                        resized.save(dst_path, format=save_format, quality=quality, optimize=True)
                    else:
                        resized.save(dst_path, format=save_format, optimize=True)

                success_count += 1
                prog = idx / total
                self._update_progress(prog, f"تم تحويل {idx} / {total} ({int(prog * 100)}%) - {filename}")
                self.log(f"✔ [{idx}/{total}] {filename}: {orig_w}x{orig_h} -> {new_w}x{new_h}")

            except Exception as e:
                error_count += 1
                self.log(f"❌ خطأ في {filename}: {e}")

        elapsed = time.time() - start_time
        self._on_conversion_complete(success_count, error_count, total, elapsed)

    def _update_progress(self, progress_val, status_text):
        self.after(0, lambda: self._apply_progress(progress_val, status_text))

    def _apply_progress(self, progress_val, status_text):
        self.progress_bar.set(progress_val)
        self.status_label.configure(text=status_text)

    def _on_conversion_complete(self, success_count, error_count, total, elapsed):
        self.after(0, lambda: self._apply_complete(success_count, error_count, total, elapsed))

    def _apply_complete(self, success_count, error_count, total, elapsed):
        self.is_converting = False
        self.start_btn.configure(state="normal", text="🚀 بدء التحويل (Start Conversion)")
        self.open_output_btn.configure(state="normal", fg_color="#2b7a44")
        self.progress_bar.set(1.0)
        self.status_label.configure(
            text=f"✅ اكتمل التحويل بنجاح! تم تحويل {success_count} صورة خلال {elapsed:.1f} ثانية."
        )

        self.log("\n==========================================")
        self.log(f"✅ انتهت العملية بنجاح!")
        self.log(f"تم تحويل: {success_count} من {total} صورة")
        if error_count > 0:
            self.log(f"فشل: {error_count} صورة")
        self.log(f"الوقت المستغرق: {elapsed:.2f} ثانية")
        self.log(f"مسار المجلد: {self.output_dir}")
        self.log("==========================================\n")

        messagebox.showinfo(
            "اكتمل التحويل",
            f"تم تحويل {success_count} صورة بنجاح إلى مقاس الراو!\n\nالمجلد: {self.output_dir}"
        )

if __name__ == "__main__":
    app = WebtoonResizerApp()
    app.mainloop()
