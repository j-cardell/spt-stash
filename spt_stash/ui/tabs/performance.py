#!/usr/bin/env python3
"""SPT Stash — Linux Performance & Launch Tuning tab (V4 layout with custom ToggleSwitch)."""

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...config import load_config, save_config
from ...system.hardware import (
    audit_system_dependencies,
    detect_cpu_core_allocation,
    detect_gpu_hardware,
)
from ..theme import BG, BORDER, SUCCESS, SURFACE, TEXT, TEXT_MUTED
from ..widgets import ToggleSwitch, _nav_pixmap


def setup_performance_tab(self):
    layout = QVBoxLayout(self.tab_performance)
    layout.setContentsMargins(22, 16, 22, 16)
    layout.setSpacing(14)

    cfg = load_config()
    deps = audit_system_dependencies()
    cpu_info = detect_cpu_core_allocation()
    gpu_info = detect_gpu_hardware()

    top_header = QHBoxLayout()
    header_v = QVBoxLayout()
    lbl_title = QLabel("Linux Performance & Game Launch Tuning")
    lbl_title.setStyleSheet("font-size: 18px; font-weight: 700; letter-spacing: -0.02em;")
    lbl_sub = QLabel(
        "All performance optimizations are OFF by default. Enable recommended driver flags for your hardware."
    )
    lbl_sub.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
    header_v.addWidget(lbl_title)
    header_v.addWidget(lbl_sub)
    top_header.addLayout(header_v)
    layout.addLayout(top_header)

    #  Hardware Detection Banner
    hw_banner = QFrame()
    hw_banner.setObjectName("hwBanner")
    hw_layout = QHBoxLayout(hw_banner)
    hw_layout.setContentsMargins(16, 12, 16, 12)
    hw_layout.setSpacing(16)

    lbl_gpu = QLabel(f"<b>GPU:</b> {gpu_info['vendor']} ({gpu_info['name']})")
    lbl_gpu.setStyleSheet(f"font-size: 12.5px; color: {TEXT};")
    hw_layout.addWidget(lbl_gpu)

    cpu_info = detect_cpu_core_allocation()
    lbl_cpu = QLabel(f"<b>CPU:</b> {cpu_info['model_name']} ({cpu_info['threads']} Threads)")
    lbl_cpu.setStyleSheet(f"font-size: 12.5px; color: {TEXT};")
    hw_layout.addWidget(lbl_cpu)

    deps = audit_system_dependencies()
    lbl_deps = QLabel(
        f"<b>MangoHud:</b> {'Ready' if deps['mangohud'] else 'Missing'} &nbsp;|&nbsp; "
        f"<b>GameMode:</b> {'Ready' if deps['gamemode'] else 'Missing'}"
    )
    lbl_deps.setStyleSheet(f"font-size: 12px; color: {TEXT_MUTED};")
    hw_layout.addWidget(lbl_deps)

    layout.addWidget(hw_banner)

    #  Grid of Performance Cards
    grid = QGridLayout()
    grid.setSpacing(12)

    def _create_perf_card(title_text, desc_text, switch_widget, extra_widget=None):
        card = QFrame()
        card.setObjectName("perfCard")
        card.setStyleSheet(f"""
            QFrame#perfCard {{
                background-color: {SURFACE};
                border: 1px solid {BORDER};
                border-radius: 10px;
            }}
            QFrame#perfCard QLabel {{
                background: transparent;
                border: none;
            }}
        """)
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(16, 14, 16, 14)
        c_layout.setSpacing(10)

        head_row = QHBoxLayout()
        head_row.setSpacing(10)
        lbl_h = QLabel(title_text)
        lbl_h.setStyleSheet(f"font-weight: 700; font-size: 13px; color: {TEXT};")
        head_row.addWidget(lbl_h)
        head_row.addStretch()
        head_row.addWidget(switch_widget)
        c_layout.addLayout(head_row)

        lbl_d = QLabel(desc_text)
        lbl_d.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11.5px; line-height: 1.4;")
        lbl_d.setWordWrap(True)
        c_layout.addWidget(lbl_d)

        if extra_widget:
            c_layout.addWidget(extra_widget)

        c_layout.addStretch()
        return card

    # Card 1: MangoHud (0, 0)
    self.chk_perf_mangohud = ToggleSwitch()
    self.chk_perf_mangohud.setChecked(cfg.get("enable_mangohud", False) and deps["mangohud"])
    card_mangohud = _create_perf_card(
        "MangoHud Performance Overlay",
        "Displays real-time FPS, frametime graphs, CPU/GPU temperatures, and VRAM usage over Tarkov (MANGOHUD=1).",
        self.chk_perf_mangohud,
    )
    grid.addWidget(card_mangohud, 0, 0)

    # Card 2: FSR 4 Upgrade (0, 1)
    self.chk_perf_fsr4 = ToggleSwitch()
    self.chk_perf_fsr4.setChecked(cfg.get("enable_fsr4", False))
    card_fsr4 = _create_perf_card(
        "AMD FSR 4 Upscaling Upgrade",
        "Upgrades Tarkov's in-game upscaler to FSR 4 using Proton-GE / Valve Proton (PROTON_FSR4_UPGRADE=1).",
        self.chk_perf_fsr4,
    )
    grid.addWidget(card_fsr4, 0, 1)

    # Card 3: DXVK Async & RADV (1, 0)
    self.chk_perf_dxvk = ToggleSwitch()
    self.chk_perf_dxvk.setChecked(cfg.get("enable_dxvk_async", False))
    dxvk_desc = (
        "Compiles graphics shaders asynchronously in background threads to eliminate scope-in micro-stutters (DXVK_ASYNC=1, RADV_PERFTEST=gpl)."
        if gpu_info["vendor"] == "AMD"
        else "Compiles graphics shaders asynchronously in background threads to eliminate scope-in micro-stutters (DXVK_ASYNC=1)."
    )
    card_dxvk = _create_perf_card("DXVK Async & Shader Caching", dxvk_desc, self.chk_perf_dxvk)
    grid.addWidget(card_dxvk, 1, 0)

    # Card 4: CPU Core Isolation (1, 1)
    self.chk_perf_cpu = ToggleSwitch()
    self.chk_perf_cpu.setChecked(cfg.get("enable_cpu_pinning", False))

    cpu_extra = QWidget()
    cpu_extra.setStyleSheet("background: transparent;")
    cpu_extra_lay = QVBoxLayout(cpu_extra)
    cpu_extra_lay.setContentsMargins(0, 0, 0, 0)
    cpu_extra_lay.setSpacing(8)

    cores_box = QHBoxLayout()
    cores_box.setSpacing(8)
    lbl_srv = QLabel("Server:")
    lbl_srv.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11.5px; font-weight: 600;")
    cores_box.addWidget(lbl_srv)
    self.txt_server_cores = QLineEdit(cfg.get("server_cpu_cores", cpu_info["server_cores"]))
    self.txt_server_cores.setFixedWidth(70)
    self.txt_server_cores.setStyleSheet("padding: 4px 6px; font-size: 11.5px;")
    cores_box.addWidget(self.txt_server_cores)

    lbl_cli = QLabel("Client:")
    lbl_cli.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11.5px; font-weight: 600;")
    cores_box.addWidget(lbl_cli)
    self.txt_client_cores = QLineEdit(cfg.get("client_cpu_cores", cpu_info["client_cores"]))
    self.txt_client_cores.setFixedWidth(70)
    self.txt_client_cores.setStyleSheet("padding: 4px 6px; font-size: 11.5px;")
    cores_box.addWidget(self.txt_client_cores)

    btn_auto_cpu = QPushButton("Auto")
    btn_auto_cpu.setIcon(QIcon(_nav_pixmap("performance", size=14, color=TEXT_MUTED)))
    btn_auto_cpu.setIconSize(QSize(14, 14))
    btn_auto_cpu.setProperty("role", "ghost")
    btn_auto_cpu.setProperty("size", "sm")
    btn_auto_cpu.clicked.connect(lambda: self.auto_detect_cpu_allocation_ui())
    cores_box.addWidget(btn_auto_cpu)
    cores_box.addStretch()
    cpu_extra_lay.addLayout(cores_box)

    self.lbl_cpu_detected_info = QLabel(
        f"<small style='color: {TEXT_MUTED};'>Detected {cpu_info['threads']} threads on {cpu_info['model_name']}.</small>"
    )
    cpu_extra_lay.addWidget(self.lbl_cpu_detected_info)

    card_cpu = _create_perf_card(
        "CPU Core Isolation (taskset)",
        "Isolates the Tarkov game client and SPT Server onto dedicated CPU affinity cores to prevent CPU scheduling contention.",
        self.chk_perf_cpu,
        extra_widget=cpu_extra,
    )
    grid.addWidget(card_cpu, 1, 1)

    # Card 5: NVIDIA NVAPI (2, 0)
    self.chk_perf_nvidia = ToggleSwitch()
    self.chk_perf_nvidia.setChecked(cfg.get("enable_nvidia_opts", False))
    card_nvidia = _create_perf_card(
        "NVIDIA Drivers & Threaded Optimizations",
        "Enables PROTON_ENABLE_NVAPI=1, DXVK_ENABLE_NVAPI=1, and __GL_THREADED_OPTIMIZATIONS=1 for NVIDIA GPUs.",
        self.chk_perf_nvidia,
    )
    grid.addWidget(card_nvidia, 2, 0)

    # Card 6: Feral GameMode (2, 1)
    self.chk_perf_gamemode = ToggleSwitch()
    self.chk_perf_gamemode.setChecked(cfg.get("enable_gamemode", False) and deps["gamemode"])
    card_gamemode = _create_perf_card(
        "Feral GameMode Daemon",
        "Requests the Linux kernel to apply maximum CPU governor performance, I/O priorities, and process niceness (gamemoderun).",
        self.chk_perf_gamemode,
    )
    grid.addWidget(card_gamemode, 2, 1)

    layout.addLayout(grid)
    layout.addStretch()

    # Apply Button
    btn_apply = QPushButton("Save && Apply (takes effect on next Start / Launch)")
    btn_apply.setIcon(QIcon(_nav_pixmap("performance", size=14, color=BG)))
    btn_apply.setIconSize(QSize(14, 14))
    btn_apply.setProperty("role", "primary")
    btn_apply.setProperty("size", "lg")
    btn_apply.setFixedHeight(40)
    btn_apply.clicked.connect(self.save_and_apply_performance_settings)
    layout.addWidget(btn_apply)


def save_and_apply_performance_settings(self):
    cfg = load_config()
    cfg["enable_mangohud"] = self.chk_perf_mangohud.isChecked()
    cfg["enable_fsr4"] = self.chk_perf_fsr4.isChecked()
    cfg["enable_dxvk_async"] = self.chk_perf_dxvk.isChecked()
    cfg["enable_cpu_pinning"] = self.chk_perf_cpu.isChecked()
    cfg["enable_nvidia_opts"] = self.chk_perf_nvidia.isChecked()
    cfg["enable_gamemode"] = self.chk_perf_gamemode.isChecked()
    cfg["server_cpu_cores"] = self.txt_server_cores.text().strip() or "0-7"
    cfg["client_cpu_cores"] = self.txt_client_cores.text().strip() or "8-31"
    save_config(cfg)

    if hasattr(self, "toast"):
        self.toast.success("Performance settings saved. They apply the next time you start the server or launch SPT.")
    else:
        QMessageBox.information(
            self,
            "Performance Settings Applied",
            "Performance tuning options have been saved. They apply the next time you start the server or launch SPT.",
        )


def auto_detect_cpu_allocation_ui(self):
    info = detect_cpu_core_allocation()
    self.txt_server_cores.setText(info["server_cores"])
    self.txt_client_cores.setText(info["client_cores"])
    self.lbl_cpu_detected_info.setText(
        f"<small style='color: {SUCCESS};'>Auto-Detected: <b>{info['model_name']}</b> ({info['threads']} Threads).</small>"
    )
    if hasattr(self, "toast"):
        self.toast.success(f"CPU Auto-Detected: {info['threads']} Threads")
    else:
        QMessageBox.information(
            self,
            "CPU Allocation Auto-Detected",
            f"Detected CPU: {info['model_name']}\nTotal Threads: {info['threads']}\n\nRecommended Server Cores: {info['server_cores']}\nRecommended Client Cores: {info['client_cores']}\n\nValues populated into Settings!",
        )
