import os
import sys
import time
import re
from PIL import Image, ImageFilter, ImageEnhance

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QGroupBox, QLabel, QLineEdit, QPushButton, QComboBox,
    QSpinBox, QCheckBox, QProgressBar, QTabWidget, QFileDialog,
    QMessageBox, QTextEdit
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QIcon

def natural_sort_key(s):
    """Sort filenames with embedded numbers naturally (1, 2, 10 instead of 1, 10, 2)."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

STYLE_SHEET = """
QMainWindow, QWidget {
    background-color: #F8FAF9;
    color: #1F2925;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 12px;
}

/* Tabs */
QTabWidget::pane {
    border: 1px solid #D1DBD5;
    background: #FFFFFF;
    border-radius: 4px;
    top: -1px;
}
QTabBar::tab {
    background: #E8ECE9;
    color: #333333;
    padding: 6px 14px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    font-weight: 500;
}
QTabBar::tab:selected {
    background: #B8F9AE;
    color: #0E4B17;
    font-weight: bold;
}
QTabBar::tab:hover:!selected {
    background: #DCE3DE;
}

/* Group Boxes */
QGroupBox {
    border: 1px solid #D1DBD5;
    border-radius: 6px;
    margin-top: 14px;
    padding-top: 12px;
    padding-bottom: 8px;
    padding-left: 8px;
    padding-right: 8px;
    font-weight: bold;
    background-color: #FFFFFF;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 4px;
    color: #18221D;
}

/* Input Fields & Combos */
QLineEdit, QSpinBox, QComboBox {
    border: 1px solid #BAC6C0;
    border-radius: 4px;
    padding: 4px 6px;
    background-color: #FFFFFF;
    color: #1A211D;
    selection-background-color: #26EE9F;
    selection-color: #000000;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
    border: 1px solid #26EE9F;
}

/* Buttons */
QPushButton {
    background-color: #26EE9F;
    color: #06311D;
    font-weight: bold;
    border: 1px solid #14D085;
    border-radius: 4px;
    padding: 5px 14px;
    min-height: 22px;
}
QPushButton:hover {
    background-color: #1FE092;
}
QPushButton:pressed {
    background-color: #17BE7B;
}
QPushButton:disabled {
    background-color: #DFE4E1;
    color: #8C9992;
    border-color: #CDD4D0;
}

/* Progress Bar */
QProgressBar {
    border: 1px solid #BAC6C0;
    border-radius: 4px;
    text-align: center;
    font-weight: bold;
    color: #000000;
    background-color: #EBF0EC;
    height: 22px;
}
QProgressBar::chunk {
    background-color: #26EE71;
    border-radius: 3px;
}

/* Checkboxes */
QCheckBox {
    spacing: 6px;
    font-weight: normal;
}
QCheckBox::indicator {
    width: 15px;
    height: 15px;
    border: 1px solid #BAC6C0;
    border-radius: 3px;
    background-color: #FFFFFF;
}
QCheckBox::indicator:checked {
    background-color: #26EE9F;
    border-color: #14D085;
}
"""

class ConversionWorker(QThread):
    progress_changed = Signal(int, str)
    finished = Signal(int, int, float, str)
    log_message = Signal(str)

    def __init__(self, source_dir, output_dir, target_width, slice_height,
                 process_mode, save_format, quality, enhance_settings):
        super().__init__()
        self.source_dir = source_dir
        self.output_dir = output_dir
        self.target_width = target_width
        self.slice_height = slice_height
        self.process_mode = process_mode  # "exact_raw_slices" or "resize_only"
        self.save_format = save_format
        self.quality = quality
        self.enhance_settings = enhance_settings

    def run(self):
        start_time = time.time()
        os.makedirs(self.output_dir, exist_ok=True)

        supported_exts = ('.jpg', '.jpeg', '.png', '.webp', '.bmp')
        files = [f for f in os.listdir(self.source_dir) if f.lower().endswith(supported_exts)]
        files.sort(key=natural_sort_key)

        total_files = len(files)
        if total_files == 0:
            self.finished.emit(0, 0, 0, self.output_dir)
            return

        enable_enhance = self.enhance_settings.get('enabled', False)
        sharp_strength = self.enhance_settings.get('sharpness', 6) / 5.0
        contrast_strength = self.enhance_settings.get('contrast', 5) / 5.0
        denoise = self.enhance_settings.get('denoise', False)
        upscale_2x = self.enhance_settings.get('upscale_2x', False)

        final_width = self.target_width * 2 if upscale_2x else self.target_width
        final_slice_height = self.slice_height * 2 if upscale_2x else self.slice_height
        out_ext = ".jpg" if self.save_format == "JPEG" else ".png" if self.save_format == "PNG" else ".webp"

        def process_image(img_path):
            with Image.open(img_path) as im:
                orig_w, orig_h = im.size
                new_w = final_width
                new_h = int(round(orig_h * (final_width / float(orig_w))))

                # Handle transparency for JPEG
                if self.save_format == "JPEG" and im.mode in ("RGBA", "LA", "P"):
                    bg = Image.new("RGB", im.size, (255, 255, 255))
                    if im.mode == "P":
                        im = im.convert("RGBA")
                    bg.paste(im, mask=im.split()[-1] if im.mode == "RGBA" else None)
                    p_img = bg
                elif im.mode != "RGB" and self.save_format == "JPEG":
                    p_img = im.convert("RGB")
                else:
                    p_img = im.copy()

                # Resample with Lanczos
                resized = p_img.resize((new_w, new_h), Image.Resampling.LANCZOS)

                # Quality enhancement pipeline
                if enable_enhance:
                    if denoise:
                        resized = resized.filter(ImageFilter.SMOOTH)

                    unsharp_radius = 1.0 * sharp_strength
                    unsharp_percent = int(115 * sharp_strength)
                    resized = resized.filter(
                        ImageFilter.UnsharpMask(radius=unsharp_radius, percent=unsharp_percent, threshold=2)
                    )

                    if contrast_strength != 1.0:
                        contraster = ImageEnhance.Contrast(resized)
                        resized = contraster.enhance(1.0 + (contrast_strength - 1.0) * 0.1)

                    if sharp_strength != 1.0:
                        sharpener = ImageEnhance.Sharpness(resized)
                        resized = sharpener.enhance(1.0 + (sharp_strength - 1.0) * 0.15)

                return resized

        success_count = 0
        error_count = 0

        # MODE 1: Exact Raw Slicing (690 x 1600)
        if self.process_mode == "exact_raw_slices":
            self.log_message.emit(f"Mode: Exact Raw Slices ({final_width}x{final_slice_height}px)")
            self.log_message.emit(f"Quality: {self.quality}% | Format: {self.save_format}")

            buffer_imgs = []
            buffer_h = 0
            slice_idx = 1

            for idx, filename in enumerate(files, start=1):
                src_path = os.path.join(self.source_dir, filename)
                try:
                    img = process_image(src_path)
                    buffer_imgs.append(img)
                    buffer_h += img.height

                    # While we have at least one full slice_height in buffer
                    while buffer_h >= final_slice_height:
                        strip = Image.new("RGB", (final_width, final_slice_height), (255, 255, 255))
                        y_off = 0
                        needed = final_slice_height
                        new_buffer_imgs = []

                        for b in buffer_imgs:
                            if needed <= 0:
                                new_buffer_imgs.append(b)
                            elif b.height <= needed:
                                strip.paste(b, (0, y_off))
                                y_off += b.height
                                needed -= b.height
                                b.close()
                            else:
                                # Crop the portion needed
                                part = b.crop((0, 0, final_width, needed))
                                strip.paste(part, (0, y_off))
                                part.close()
                                y_off += needed

                                # Keep the remainder in buffer
                                rem = b.crop((0, needed, final_width, b.height))
                                b.close()
                                new_buffer_imgs.append(rem)
                                needed = 0

                        out_name = f"{slice_idx:03d}{out_ext}"
                        out_path = os.path.join(self.output_dir, out_name)
                        if self.save_format in ("JPEG", "WEBP"):
                            strip.save(out_path, format=self.save_format, quality=self.quality, optimize=True)
                        else:
                            strip.save(out_path, format=self.save_format, optimize=True)
                        strip.close()

                        self.log_message.emit(f"Generated Slice {out_name} ({final_width}x{final_slice_height})")
                        slice_idx += 1
                        buffer_imgs = new_buffer_imgs
                        buffer_h -= final_slice_height

                    prog = int((idx / float(total_files)) * 100)
                    self.progress_changed.emit(prog, f"Processing {idx} of {total_files} ({prog}%) - {filename}")

                except Exception as e:
                    error_count += 1
                    self.log_message.emit(f"ERROR: {filename} - {str(e)}")

            # Flush the last remaining remainder slice
            if buffer_imgs and buffer_h > 0:
                strip = Image.new("RGB", (final_width, buffer_h), (255, 255, 255))
                y_off = 0
                for b in buffer_imgs:
                    strip.paste(b, (0, y_off))
                    y_off += b.height
                    b.close()

                out_name = f"{slice_idx:03d}{out_ext}"
                out_path = os.path.join(self.output_dir, out_name)
                if self.save_format in ("JPEG", "WEBP"):
                    strip.save(out_path, format=self.save_format, quality=self.quality, optimize=True)
                else:
                    strip.save(out_path, format=self.save_format, optimize=True)
                strip.close()

                self.log_message.emit(f"Generated Final Slice {out_name} ({final_width}x{buffer_h})")
                success_count = slice_idx
            else:
                success_count = slice_idx - 1

        # MODE 2: Individual Image Resizing (No Slicing)
        else:
            self.log_message.emit("Mode: Keep Original Slices (Resize Only)")
            for idx, filename in enumerate(files, start=1):
                src_path = os.path.join(self.source_dir, filename)
                base_name, _ = os.path.splitext(filename)
                dst_path = os.path.join(self.output_dir, base_name + out_ext)

                try:
                    img = process_image(src_path)
                    if self.save_format in ("JPEG", "WEBP"):
                        img.save(dst_path, format=self.save_format, quality=self.quality, optimize=True)
                    else:
                        img.save(dst_path, format=self.save_format, optimize=True)
                    img.close()

                    success_count += 1
                    prog = int((idx / float(total_files)) * 100)
                    self.progress_changed.emit(prog, f"Processing {idx} of {total_files} ({prog}%) - {filename}")
                    self.log_message.emit(f"OK: {filename}")

                except Exception as e:
                    error_count += 1
                    self.log_message.emit(f"ERROR: {filename} - {str(e)}")

        elapsed = time.time() - start_time
        self.finished.emit(success_count, error_count, elapsed, self.output_dir)


class SmartResizerWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("SmartStitch By MechTechnology [3.1] - Webtoon Raw Resizer")
        self.resize(500, 490)
        self.setMinimumSize(480, 470)

        # Set Icon
        app_dir = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(app_dir, "assets", "icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.setAcceptDrops(True)
        self.worker = None

        self._build_ui()
        self.setStyleSheet(STYLE_SHEET)

    def _build_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(8, 0, 8, 8)
        main_layout.setSpacing(6)

        # Tab Widget
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        self.basic_tab = QWidget()
        self.enhance_tab = QWidget()
        self.advanced_tab = QWidget()

        self.tabs.addTab(self.basic_tab, "Basic")
        self.tabs.addTab(self.enhance_tab, "Quality Enhance")
        self.tabs.addTab(self.advanced_tab, "Advanced")

        self._build_basic_tab()
        self._build_enhance_tab()
        self._build_advanced_tab()

        # Current Status Group (Always visible at the bottom)
        status_group = QGroupBox("Current Status")
        status_layout = QVBoxLayout(status_group)
        status_layout.setContentsMargins(6, 8, 6, 6)
        status_layout.setSpacing(6)

        h_status = QHBoxLayout()
        self.status_field = QLineEdit()
        self.status_field.setReadOnly(True)
        self.status_field.setText("Idle - Ready for conversion")
        h_status.addWidget(self.status_field, stretch=3)

        self.start_btn = QPushButton("Start Process")
        self.start_btn.setMinimumHeight(28)
        self.start_btn.clicked.connect(self.start_conversion)
        h_status.addWidget(self.start_btn, stretch=1)
        status_layout.addLayout(h_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        status_layout.addWidget(self.progress_bar)

        main_layout.addWidget(status_group)

    def _build_basic_tab(self):
        layout = QVBoxLayout(self.basic_tab)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Input / Output Group
        io_group = QGroupBox("Input/Output Settings")
        io_layout = QVBoxLayout(io_group)
        io_layout.setContentsMargins(6, 8, 6, 6)
        io_layout.setSpacing(4)

        io_layout.addWidget(QLabel("Input Path"))
        h_in = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Select or drag & drop webtoon folder...")
        self.input_field.textChanged.connect(self.on_input_changed)
        h_in.addWidget(self.input_field, stretch=3)

        self.browse_btn = QPushButton("Browse")
        self.browse_btn.clicked.connect(self.browse_input_folder)
        h_in.addWidget(self.browse_btn, stretch=1)
        io_layout.addLayout(h_in)

        io_layout.addWidget(QLabel("Output Path"))
        self.output_field = QLineEdit()
        self.output_field.setPlaceholderText("Output folder will be created automatically...")
        io_layout.addWidget(self.output_field)

        layout.addWidget(io_group)

        # General Settings Group
        gen_group = QGroupBox("General Settings")
        gen_layout = QGridLayout(gen_group)
        gen_layout.setContentsMargins(6, 8, 6, 6)
        gen_layout.setHorizontalSpacing(10)
        gen_layout.setVerticalSpacing(6)

        # Row 0: File Type & Quality
        gen_layout.addWidget(QLabel("Output File Type"), 0, 0)
        self.type_combo = QComboBox()
        self.type_combo.addItems([".jpg", ".png", ".webp"])
        gen_layout.addWidget(self.type_combo, 1, 0)

        gen_layout.addWidget(QLabel("Lossy File Quality [1-100%]"), 0, 1)
        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(1, 100)
        self.quality_spin.setValue(95)
        gen_layout.addWidget(self.quality_spin, 1, 1)

        # Row 2: Slice Height & Process Mode
        gen_layout.addWidget(QLabel("Raw Slice Height (Exact)"), 2, 0)
        self.height_spin = QSpinBox()
        self.height_spin.setRange(100, 50000)
        self.height_spin.setSingleStep(100)
        self.height_spin.setValue(1600)  # Default: exact official Naver raw slice height!
        gen_layout.addWidget(self.height_spin, 3, 0)

        gen_layout.addWidget(QLabel("Process Mode"), 2, 1)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems([
            "Exact 690x1600 Raw Slices",
            "Keep Original Image Slices"
        ])
        self.mode_combo.currentIndexChanged.connect(self.on_mode_combo_changed)
        gen_layout.addWidget(self.mode_combo, 3, 1)

        # Row 4: Target Width & Custom Width
        gen_layout.addWidget(QLabel("Target Raw Width"), 4, 0)
        self.width_combo = QComboBox()
        self.width_combo.addItems([
            "690 px (Naver Raw Standard)",
            "720 px (Webtoon Standard)",
            "800 px (Kakao / Tapas)",
            "Custom Width"
        ])
        self.width_combo.currentIndexChanged.connect(self.on_width_combo_changed)
        gen_layout.addWidget(self.width_combo, 5, 0)

        gen_layout.addWidget(QLabel("Custom Width (px)"), 4, 1)
        self.custom_width_spin = QSpinBox()
        self.custom_width_spin.setRange(100, 10000)
        self.custom_width_spin.setValue(690)
        gen_layout.addWidget(self.custom_width_spin, 5, 1)

        # Row 6: Quality Boost Checkbox
        gen_layout.addWidget(QLabel("Quality Boost"), 6, 0)
        self.quick_enhance_check = QCheckBox("Enable AI Quality Boost ✨")
        self.quick_enhance_check.setChecked(True)
        self.quick_enhance_check.stateChanged.connect(self.on_quick_enhance_changed)
        gen_layout.addWidget(self.quick_enhance_check, 7, 0)

        layout.addWidget(gen_group)
        layout.addStretch()

    def _build_enhance_tab(self):
        layout = QVBoxLayout(self.enhance_tab)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        enhance_group = QGroupBox("Image Quality & AI Enhancement Settings")
        e_layout = QVBoxLayout(enhance_group)
        e_layout.setContentsMargins(8, 10, 8, 8)
        e_layout.setSpacing(8)

        self.master_enhance_check = QCheckBox("Enable Quality Enhancement Engine")
        self.master_enhance_check.setChecked(True)
        self.master_enhance_check.setStyleSheet("font-weight: bold; font-size: 13px; color: #0E4B17;")
        self.master_enhance_check.stateChanged.connect(self.on_master_enhance_changed)
        e_layout.addWidget(self.master_enhance_check)

        # Preset Dropdown
        e_layout.addWidget(QLabel("Enhancement Preset:"))
        self.preset_combo = QComboBox()
        self.preset_combo.addItems([
            "Full Auto Webtoon Raw (Line Sharpening + Gentle Contrast + Denoise)",
            "Smart Line & Text Sharpening (Crisp Speech Bubbles & Inking)",
            "De-Artifact & Denoise (Clean Screenshot Compression Noise)",
            "2x Super Resolution (2x Upscale with Detail Preservation)"
        ])
        self.preset_combo.currentIndexChanged.connect(self.on_preset_preset_changed)
        e_layout.addWidget(self.preset_combo)

        # Sliders / Controls Grid
        grid = QGridLayout()
        grid.setSpacing(6)

        grid.addWidget(QLabel("Sharpening Strength:"), 0, 0)
        self.sharp_spin = QSpinBox()
        self.sharp_spin.setRange(1, 10)
        self.sharp_spin.setValue(6)
        grid.addWidget(self.sharp_spin, 0, 1)

        grid.addWidget(QLabel("Contrast & Inking Density:"), 1, 0)
        self.contrast_spin = QSpinBox()
        self.contrast_spin.setRange(1, 10)
        self.contrast_spin.setValue(5)
        grid.addWidget(self.contrast_spin, 1, 1)

        e_layout.addLayout(grid)

        # Denoise Checkbox
        self.denoise_check = QCheckBox("Denoise Backgrounds & Compression Banding")
        self.denoise_check.setChecked(True)
        e_layout.addWidget(self.denoise_check)

        # 2x Super Res Checkbox
        self.upscale_check = QCheckBox("2x Super Resolution Upscale")
        self.upscale_check.setChecked(False)
        e_layout.addWidget(self.upscale_check)

        # Info Box
        info_label = QLabel(
            "Tip: Screenshots from phones soften line art and dialogue text.\n"
            "This engine restores crisp ink outlines and removes JPEG compression noise, giving clean raw results."
        )
        info_label.setStyleSheet("color: #4A6356; background-color: #F1F6F3; border: 1px dashed #BAC6C0; border-radius: 4px; padding: 6px;")
        info_label.setWordWrap(True)
        e_layout.addWidget(info_label)

        layout.addWidget(enhance_group)
        layout.addStretch()

    def _build_advanced_tab(self):
        layout = QVBoxLayout(self.advanced_tab)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        adv_group = QGroupBox("Advanced & Post-Process Settings")
        adv_layout = QVBoxLayout(adv_group)
        adv_layout.setContentsMargins(6, 8, 6, 6)
        adv_layout.setSpacing(6)

        self.auto_open_check = QCheckBox("Auto-open output folder on process completion")
        self.auto_open_check.setChecked(True)
        adv_layout.addWidget(self.auto_open_check)

        adv_layout.addWidget(QLabel("Process Console Log:"))
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("background-color: #FAFAFA; font-family: Consolas; font-size: 11px;")
        adv_layout.addWidget(self.log_text)

        layout.addWidget(adv_group)

    def on_input_changed(self, text):
        path = text.strip().strip('"')
        if os.path.isdir(path):
            folder_name = os.path.basename(os.path.normpath(path))
            parent_dir = os.path.dirname(os.path.normpath(path))
            w = self.custom_width_spin.value()
            h = self.height_spin.value()
            enh_tag = " [Enhanced]" if self.master_enhance_check.isChecked() else ""
            mode_tag = f" [{w}x{h} Raw]" if self.mode_combo.currentIndex() == 0 else f" [{w}px]"
            self.output_field.setText(os.path.join(parent_dir, f"{folder_name}{mode_tag}{enh_tag}"))
            self.status_field.setText(f"Folder loaded: {folder_name}")

    def on_width_combo_changed(self, index):
        if index == 0:
            self.custom_width_spin.setValue(690)
        elif index == 1:
            self.custom_width_spin.setValue(720)
        elif index == 2:
            self.custom_width_spin.setValue(800)
        self.on_input_changed(self.input_field.text())

    def on_mode_combo_changed(self, index):
        self.on_input_changed(self.input_field.text())

    def on_quick_enhance_changed(self, state):
        self.master_enhance_check.setChecked(state == Qt.Checked)
        self.on_input_changed(self.input_field.text())

    def on_master_enhance_changed(self, state):
        self.quick_enhance_check.setChecked(state == Qt.Checked)
        self.on_input_changed(self.input_field.text())

    def on_preset_preset_changed(self, index):
        if index == 0:  # Full Auto
            self.sharp_spin.setValue(6)
            self.contrast_spin.setValue(5)
            self.denoise_check.setChecked(True)
            self.upscale_check.setChecked(False)
        elif index == 1:  # Line sharpness
            self.sharp_spin.setValue(8)
            self.contrast_spin.setValue(6)
            self.denoise_check.setChecked(False)
            self.upscale_check.setChecked(False)
        elif index == 2:  # Denoise
            self.sharp_spin.setValue(4)
            self.contrast_spin.setValue(4)
            self.denoise_check.setChecked(True)
            self.upscale_check.setChecked(False)
        elif index == 3:  # 2x Super Res
            self.sharp_spin.setValue(7)
            self.contrast_spin.setValue(5)
            self.denoise_check.setChecked(True)
            self.upscale_check.setChecked(True)

    def browse_input_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Webtoon Folder")
        if folder:
            self.input_field.setText(folder)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if os.path.isfile(path):
                path = os.path.dirname(path)
            self.input_field.setText(path)

    def start_conversion(self):
        src = self.input_field.text().strip().strip('"')
        if not src or not os.path.isdir(src):
            QMessageBox.warning(self, "Warning", "Please select a valid input folder first.")
            return

        dst = self.output_field.text().strip().strip('"')
        if not dst:
            dst = os.path.join(src, "output")
        os.makedirs(dst, exist_ok=True)

        target_w = self.custom_width_spin.value()
        slice_h = self.height_spin.value()
        process_mode = "exact_raw_slices" if self.mode_combo.currentIndex() == 0 else "resize_only"

        # File format
        type_str = self.type_combo.currentText()
        if type_str == ".jpg":
            save_format = "JPEG"
        elif type_str == ".png":
            save_format = "PNG"
        elif type_str == ".webp":
            save_format = "WEBP"
        else:
            save_format = "JPEG"

        quality = self.quality_spin.value()

        enhance_settings = {
            'enabled': self.master_enhance_check.isChecked(),
            'sharpness': self.sharp_spin.value(),
            'contrast': self.contrast_spin.value(),
            'denoise': self.denoise_check.isChecked(),
            'upscale_2x': self.upscale_check.isChecked()
        }

        self.start_btn.setEnabled(False)
        self.browse_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_field.setText("Starting process...")
        self.log_text.append(f"\n--- Starting Process: {src} -> {dst} ---")

        self.worker = ConversionWorker(
            src, dst, target_w, slice_h, process_mode, save_format, quality, enhance_settings
        )
        self.worker.progress_changed.connect(self.on_worker_progress)
        self.worker.log_message.connect(self.on_worker_log)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.start()

    def on_worker_progress(self, val, msg):
        self.progress_bar.setValue(val)
        self.status_field.setText(msg)

    def on_worker_log(self, msg):
        self.log_text.append(msg)

    def on_worker_finished(self, success_count, error_count, elapsed, out_dir):
        self.start_btn.setEnabled(True)
        self.browse_btn.setEnabled(True)
        self.progress_bar.setValue(100)
        self.status_field.setText(f"Idle - Process completed in {elapsed:.3f} seconds")

        self.log_text.append(f"\nProcess completed in {elapsed:.3f} seconds.")
        self.log_text.append(f"Successfully generated: {success_count} raw slices ({self.custom_width_spin.value()}x{self.height_spin.value()}).")
        if error_count > 0:
            self.log_text.append(f"Errors: {error_count} files.")

        if self.auto_open_check.isChecked() and os.path.exists(out_dir):
            os.startfile(out_dir)

        QMessageBox.information(
            self,
            "Process Finished",
            f"Successfully generated {success_count} raw slices ({self.custom_width_spin.value()}x{self.height_spin.value()}) in {elapsed:.2f} seconds!\n\nOutput: {out_dir}"
        )

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SmartResizerWindow()
    window.show()
    sys.exit(app.exec())
