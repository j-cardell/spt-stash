#!/usr/bin/env python3
"""SPT Stash — Linux Performance & Launch Tuning tab."""

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ...config import load_config, save_config
from ...paths import find_spt_root
from ...system.hardware import (
    audit_system_dependencies,
    detect_cpu_core_allocation,
    detect_gpu_hardware,
)


def setup_performance_tab(self):
    layout = QVBoxLayout(self.tab_performance)
    layout.setContentsMargins(14, 14, 14, 14)
    layout.setSpacing(10)

    cfg = load_config()
    deps = audit_system_dependencies()
    cpu_info = detect_cpu_core_allocation()
    gpu_info = detect_gpu_hardware()

    # Header Title & Hardware Detection Banner
    top_header = QHBoxLayout()
    header_v = QVBoxLayout()
    lbl_title = QLabel("⚡ Linux Performance && Game Launch Tuning")
    lbl_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #89b4fa;")
    lbl_sub = QLabel(
        "All performance optimizations are OFF by default. Enable recommended driver flags for your hardware."
    )
    lbl_sub.setStyleSheet("color: #a6adc8; font-size: 11px;")
    header_v.addWidget(lbl_title)
    header_v.addWidget(lbl_sub)

    lbl_hw_badge = QLabel(f"🎮 <b>GPU:</b> {gpu_info['vendor']} ({gpu_info['name'][:32]})")
    lbl_hw_badge.setStyleSheet(
        "background-color: #313244; color: #a6e3a1; border: 1px solid #45475a; font-size: 11px; font-weight: bold; padding: 6px 12px; border-radius: 6px;"
    )

    top_header.addLayout(header_v)
    top_header.addStretch()
    top_header.addWidget(lbl_hw_badge)
    layout.addLayout(top_header)

    grid = QGridLayout()
    grid.setSpacing(10)

    card_style = """
        QGroupBox { font-weight: bold; color: #cdd6f4; border: 1px solid #45475a; border-radius: 8px; margin-top: 4px; padding: 10px; background-color: #1e1e2e; }
        QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: %COLOR%; }
    """

    # Card 1: MangoHud (0, 0)
    card_mangohud = QGroupBox("📊 MangoHud Performance Overlay")
    card_mangohud.setStyleSheet(card_style.replace("%COLOR%", "#89b4fa"))
    m_lay = QVBoxLayout(card_mangohud)
    m_lay.setSpacing(6)

    m_row = QHBoxLayout()
    self.chk_perf_mangohud = QCheckBox("Enable MangoHud Overlay (MANGOHUD=1)")
    self.chk_perf_mangohud.setChecked(cfg.get("enable_mangohud", False) and deps["mangohud"])
    self.chk_perf_mangohud.setStyleSheet("QCheckBox { color: #cdd6f4; font-weight: bold; font-size: 12px; }")

    lbl_m_status = QLabel(
        "<span style='color: #a6e3a1; font-weight: bold;'>🟢 mangohud</span>"
        if deps["mangohud"]
        else "<span style='color: #f38ba8; font-weight: bold;'>⚠️ missing</span>"
    )
    m_row.addWidget(self.chk_perf_mangohud)
    m_row.addStretch()
    m_row.addWidget(lbl_m_status)
    m_lay.addLayout(m_row)

    m_help = QLabel(
        "<small style='color: #a6adc8;'>Displays real-time FPS, frametime graphs, CPU/GPU temperatures, and VRAM usage over Tarkov.</small>"
    )
    m_help.setWordWrap(True)
    m_lay.addWidget(m_help)
    m_lay.addStretch()
    grid.addWidget(card_mangohud, 0, 0)

    # Card 2: FSR 4 Upgrade (0, 1)
    card_fsr4 = QGroupBox("⚡ AMD FSR 4 Upscaling Upgrade")
    card_fsr4.setStyleSheet(card_style.replace("%COLOR%", "#a6e3a1"))
    f_lay = QVBoxLayout(card_fsr4)
    f_lay.setSpacing(6)
    self.chk_perf_fsr4 = QCheckBox("Enable Proton FSR 4 Upgrade (PROTON_FSR4_UPGRADE=1)")
    self.chk_perf_fsr4.setChecked(cfg.get("enable_fsr4", False))
    self.chk_perf_fsr4.setStyleSheet("QCheckBox { color: #cdd6f4; font-weight: bold; font-size: 12px; }")
    f_help = QLabel(
        "<small style='color: #a6adc8;'>Upgrades Tarkov's in-game upscaler to FSR 4 using Proton-GE / Valve Proton.</small>"
    )
    f_help.setWordWrap(True)
    f_lay.addWidget(self.chk_perf_fsr4)
    f_lay.addWidget(f_help)
    f_lay.addStretch()
    grid.addWidget(card_fsr4, 0, 1)

    # Card 3: DXVK Async & RADV (1, 0)
    card_dxvk = QGroupBox("🚀 DXVK Async && Shader Caching")
    card_dxvk.setStyleSheet(card_style.replace("%COLOR%", "#f9e2af"))
    d_lay = QVBoxLayout(card_dxvk)
    d_lay.setSpacing(6)
    dxvk_label = (
        "Enable DXVK Async && State Cache (DXVK_ASYNC=1, RADV_PERFTEST=gpl)"
        if gpu_info["vendor"] == "AMD"
        else "Enable DXVK Async && State Cache (DXVK_ASYNC=1)"
    )
    self.chk_perf_dxvk = QCheckBox(dxvk_label)
    self.chk_perf_dxvk.setChecked(cfg.get("enable_dxvk_async", False))
    self.chk_perf_dxvk.setStyleSheet("QCheckBox { color: #cdd6f4; font-weight: bold; font-size: 12px; }")
    d_help = QLabel(
        "<small style='color: #a6adc8;'>Compiles graphics shaders asynchronously in background threads to eliminate scope-in and firefight micro-stutters.</small>"
    )
    d_help.setWordWrap(True)
    d_lay.addWidget(self.chk_perf_dxvk)
    d_lay.addWidget(d_help)
    d_lay.addStretch()
    grid.addWidget(card_dxvk, 1, 0)

    # Card 4: CPU Core Isolation (1, 1)
    card_cpu = QGroupBox("🧠 CPU Core Isolation (taskset)")
    card_cpu.setStyleSheet(card_style.replace("%COLOR%", "#cba6f7"))
    c_lay = QVBoxLayout(card_cpu)
    c_lay.setSpacing(6)

    self.chk_perf_cpu = QCheckBox("Isolate CPU Cores between Server and Client")
    self.chk_perf_cpu.setChecked(cfg.get("enable_cpu_pinning", False) and deps["taskset"])
    self.chk_perf_cpu.setStyleSheet("QCheckBox { color: #cdd6f4; font-weight: bold; font-size: 12px; }")

    btn_autodetect_cpu = QPushButton("🤖 Auto-Detect")
    btn_autodetect_cpu.setStyleSheet(
        "background-color: #313244; color: #cba6f7; border: 1px solid #45475a; font-size: 11px; font-weight: bold; padding: 3px 8px; border-radius: 4px;"
    )
    btn_autodetect_cpu.clicked.connect(self.auto_detect_cpu_allocation_ui)

    lbl_t_status = QLabel(
        "<span style='color: #a6e3a1; font-weight: bold;'>🟢 taskset</span>"
        if deps["taskset"]
        else "<span style='color: #f38ba8; font-weight: bold;'>⚠️ missing</span>"
    )

    top_cpu_row = QHBoxLayout()
    top_cpu_row.addWidget(self.chk_perf_cpu)
    top_cpu_row.addStretch()
    top_cpu_row.addWidget(lbl_t_status)
    top_cpu_row.addSpacing(8)
    top_cpu_row.addWidget(btn_autodetect_cpu)
    c_lay.addLayout(top_cpu_row)

    cores_layout = QHBoxLayout()
    lbl_s_cores = QLabel("Server Cores:")
    self.txt_server_cores = QLineEdit(cfg.get("server_cpu_cores", cpu_info["server_cores"]))
    self.txt_server_cores.setFixedWidth(80)
    lbl_c_cores = QLabel("Client Cores:")
    self.txt_client_cores = QLineEdit(cfg.get("client_cpu_cores", cpu_info["client_cores"]))
    self.txt_client_cores.setFixedWidth(80)

    cores_layout.addWidget(lbl_s_cores)
    cores_layout.addWidget(self.txt_server_cores)
    cores_layout.addSpacing(12)
    cores_layout.addWidget(lbl_c_cores)
    cores_layout.addWidget(self.txt_client_cores)
    cores_layout.addStretch()

    self.lbl_cpu_detected_info = QLabel(
        f"<small style='color: #cba6f7;'>CPU: <b>{cpu_info['model_name']}</b> ({cpu_info['threads']}T). Rec: Server ({cpu_info['server_cores']}), Client ({cpu_info['client_cores']}).</small>"
    )
    self.lbl_cpu_detected_info.setWordWrap(True)

    c_lay.addLayout(cores_layout)
    c_lay.addWidget(self.lbl_cpu_detected_info)
    c_lay.addStretch()
    grid.addWidget(card_cpu, 1, 1)

    # Card 5: NVIDIA Hardware Optimizations (2, 0)
    card_nvidia = QGroupBox("💚 NVIDIA Hardware Optimizations")
    card_nvidia.setStyleSheet(card_style.replace("%COLOR%", "#76b900"))
    n_lay = QVBoxLayout(card_nvidia)
    n_lay.setSpacing(6)
    self.chk_perf_nvidia = QCheckBox("Enable NVIDIA Drivers (NVAPI, DLSS/Reflex, Threaded Shaders)")
    self.chk_perf_nvidia.setChecked(cfg.get("enable_nvidia_opts", False))
    self.chk_perf_nvidia.setStyleSheet("QCheckBox { color: #cdd6f4; font-weight: bold; font-size: 12px; }")
    if gpu_info["vendor"] != "NVIDIA":
        self.chk_perf_nvidia.setEnabled(False)
        self.chk_perf_nvidia.setToolTip(f"NVIDIA optimizations disabled (Detected GPU: {gpu_info['vendor']})")
        n_help = QLabel(
            "<small style='color: #585b70;'>Requires an NVIDIA GeForce GPU (Detected: AMD/Intel GPU).</small>"
        )
    else:
        n_help = QLabel(
            "<small style='color: #a6adc8;'>Exports PROTON_ENABLE_NVAPI=1, DXVK_ENABLE_NVAPI=1, and __GL_THREADED_OPTIMIZATIONS=1.</small>"
        )
    n_help.setWordWrap(True)
    n_lay.addWidget(self.chk_perf_nvidia)
    n_lay.addWidget(n_help)
    n_lay.addStretch()
    grid.addWidget(card_nvidia, 2, 0)

    # Card 6: Feral GameMode (2, 1)
    card_gamemode = QGroupBox("🎮 Feral GameMode Daemon")
    card_gamemode.setStyleSheet(card_style.replace("%COLOR%", "#f38ba8"))
    g_lay = QVBoxLayout(card_gamemode)
    g_lay.setSpacing(6)

    g_row = QHBoxLayout()
    self.chk_perf_gamemode = QCheckBox("Enable GameMode Wrapper (gamemoderun)")
    self.chk_perf_gamemode.setChecked(cfg.get("enable_gamemode", False) and deps.get("gamemode", False))
    self.chk_perf_gamemode.setStyleSheet("QCheckBox { color: #cdd6f4; font-weight: bold; font-size: 12px; }")

    lbl_g_status = QLabel(
        "<span style='color: #a6e3a1; font-weight: bold;'>🟢 gamemoded</span>"
        if deps.get("gamemode", False)
        else "<span style='color: #f38ba8; font-weight: bold;'>⚠️ missing</span>"
    )
    g_row.addWidget(self.chk_perf_gamemode)
    g_row.addStretch()
    g_row.addWidget(lbl_g_status)
    g_lay.addLayout(g_row)

    g_help = QLabel(
        "<small style='color: #a6adc8;'>Requests max CPU performance governor, disk I/O priority, and disables C-state sleeping during raids.</small>"
    )
    g_help.setWordWrap(True)
    g_lay.addWidget(g_help)
    g_lay.addStretch()
    grid.addWidget(card_gamemode, 2, 1)

    layout.addLayout(grid)
    layout.addStretch()

    # Apply Button
    btn_apply = QPushButton("⚡ Save && Apply to launcher.sh && server.sh")
    btn_apply.setFixedHeight(38)
    btn_apply.setStyleSheet("""
        QPushButton { background-color: #a6e3a1; color: #11111b; font-size: 13px; font-weight: bold; border-radius: 6px; padding: 6px 16px; }
        QPushButton:hover { background-color: #b4befe; color: #11111b; }
    """)
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

    spt_dir = Path(cfg.get("spt_path", str(find_spt_root())))
    launcher_sh = Path(cfg.get("launcher_script", str(spt_dir / "launcher.sh")))
    server_sh = Path(cfg.get("server_script", str(spt_dir / "server.sh")))

    # Update launcher.sh
    if launcher_sh.exists():
        try:
            mangohud_val = 1 if cfg["enable_mangohud"] else 0
            fsr4_val = 1 if cfg["enable_fsr4"] else 0
            dxvk_val = 1 if cfg["enable_dxvk_async"] else 0
            cpu_val = 1 if cfg["enable_cpu_pinning"] else 0
            nvidia_val = 1 if cfg["enable_nvidia_opts"] else 0
            gamemode_val = 1 if cfg["enable_gamemode"] else 0
            client_cores = cfg["client_cpu_cores"]

            launcher_script_content = f"""#!/usr/bin/env bash

# Clear library path pollution from parent processes
unset LD_LIBRARY_PATH

# Performance Optimizations Config
ENABLE_CPU_PINNING={cpu_val}
CLIENT_CPU_CORES="{client_cores}"
ENABLE_DXVK_ASYNC={dxvk_val}
ENABLE_FSR4={fsr4_val}
ENABLE_MANGOHUD={mangohud_val}
ENABLE_NVIDIA_OPTS={nvidia_val}
ENABLE_GAMEMODE={gamemode_val}

# Environment Exports
if [ "$ENABLE_DXVK_ASYNC" -eq 1 ]; then export DXVK_ASYNC=1; fi
if [ "$ENABLE_FSR4" -eq 1 ]; then export WINE_FULLSCREEN_FSR=1; fi
if [ "$ENABLE_NVIDIA_OPTS" -eq 1 ]; then
export PROTON_ENABLE_NVAPI=1
export DXVK_ENABLE_NVAPI=1
export __GL_THREADED_OPTIMIZATIONS=1
fi

MANGOHUD_CMD=""
if [ "$ENABLE_MANGOHUD" -eq 1 ] && command -v mangohud &>/dev/null; then
MANGOHUD_CMD="mangohud"
fi

TASKSET_CMD=""
if [ "$ENABLE_CPU_PINNING" -eq 1 ] && command -v taskset &>/dev/null; then
TASKSET_CMD="taskset -c $CLIENT_CPU_CORES"
fi

GAMEMODE_CMD=""
if [ "$ENABLE_GAMEMODE" -eq 1 ] && command -v gamemoderun &>/dev/null; then
GAMEMODE_CMD="gamemoderun"
fi

# We don't want to run as root
if [[ "$( id -u )" -eq 0 ]]; then
echo "This script is not supposed to be run as root!" >&2
exit 1
fi

cwd="$(cd -- "$(dirname -- "${{BASH_SOURCE[0]}}")" && pwd)"
cd "${{cwd}}/SPT_Runtime" && ${{MANGOHUD_CMD}} ${{TASKSET_CMD}} ${{GAMEMODE_CMD}} ./SPT.Launcher.Linux
"""
            launcher_sh.write_text(launcher_script_content, encoding="utf-8")
            launcher_sh.chmod(0o755)
        except Exception as e:
            print(f"Error updating launcher.sh: {e}")

    # Update server.sh
    if server_sh.exists():
        try:
            cpu_val = 1 if cfg["enable_cpu_pinning"] else 0
            server_cores = cfg["server_cpu_cores"]

            server_script_content = f"""#!/usr/bin/env bash

# Clear library path pollution from parent processes
unset LD_LIBRARY_PATH

# Server Performance Optimizations Config
ENABLE_SERVER_CPU_PINNING={cpu_val}
SERVER_CPU_CORES="{server_cores}"

TASKSET_CMD=""
if [ "$ENABLE_SERVER_CPU_PINNING" -eq 1 ] && command -v taskset &>/dev/null; then
TASKSET_CMD="taskset -c $SERVER_CPU_CORES"
fi

# We don't want to run as root
if [[ "$( id -u )" -eq 0 ]]; then
echo "This script is not supposed to be run as root!" >&2
exit 1
fi

ROOT_PATH="$( cd -- "$( dirname -- "${{BASH_SOURCE[0]}}" )" &>/dev/null && pwd )"

# Universal Terminal Emulator Matrix (Distro-Agnostic)
TERMINALS=(
"xdg-terminal-exec" "x-terminal-emulator"
"alacritty" "ghostty" "foot" "terminator" "ptyxis" "cosmic-terminal"
"kgx" "konsole" "gnome-terminal" "xfce4-terminal" "kitty" "tilix"
"wezterm" "lxterminal" "xterm" "urxvt" "rxvt" "st" "termite"
)

cd "${{ROOT_PATH}}/SPT_Runtime" || exit 1

# If already in an interactive terminal, run directly
if [ -t 0 ]; then
exec ${{TASKSET_CMD}} ./SPT.Server.Linux
exit 0
fi

# Try launching in an available GUI terminal emulator
for term in "${{TERMINALS[@]}}"; do
if command -v "$term" &>/dev/null; then
    exec $term -e ${{TASKSET_CMD}} ./SPT.Server.Linux >&1
    exit 0
fi
done

# Fallback for headless / custom setups without GUI terminal emulators
echo "No GUI terminal emulator found. Starting SPT Server in background..."
exec ${{TASKSET_CMD}} ./SPT.Server.Linux > "${{ROOT_PATH}}/user/logs/server-direct.log" 2>&1 &
"""
            server_sh.write_text(server_script_content, encoding="utf-8")
            server_sh.chmod(0o755)
        except Exception as e:
            print(f"Error updating server.sh: {e}")

    QMessageBox.information(
        self,
        "⚡ Performance Settings Applied",
        "Performance tuning options have been saved and applied to launcher.sh and server.sh!",
    )


def auto_detect_cpu_allocation_ui(self):
    info = detect_cpu_core_allocation()
    self.txt_server_cores.setText(info["server_cores"])
    self.txt_client_cores.setText(info["client_cores"])
    self.lbl_cpu_detected_info.setText(
        f"<small style='color: #a6e3a1;'>🤖 Auto-Detected: <b>{info['model_name']}</b> ({info['threads']} Threads). Applied Server ({info['server_cores']}), Client ({info['client_cores']}).</small>"
    )
    QMessageBox.information(
        self,
        "🤖 CPU Allocation Auto-Detected",
        f"Detected CPU: {info['model_name']}\nTotal Threads: {info['threads']}\n\nRecommended Server Cores: {info['server_cores']}\nRecommended Client Cores: {info['client_cores']}\n\nValues populated into Settings!",
    )
