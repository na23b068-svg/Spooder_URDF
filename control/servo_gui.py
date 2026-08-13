#!/usr/bin/env python3
"""
SpiderBot Hexapod Servo Controller GUI
A professional dark-themed GUI for controlling a 12-servo hexapod (2 servos per leg)
via a PCA9685 and Arduino Nano. Features 6-direction tripod gait generation,
adjustable sweep test speeds, and a live 3D wireframe telemetry monitor.
Author: Antigravity AI Coding Assistant
"""

import tkinter as tk
from tkinter import ttk, messagebox
import serial
import serial.tools.list_ports
import threading
import time
import math

# Theme Colors (Deep Slate / Cyberpunk Theme)
COLOR_BG = "#0F172A"       # Tailwind Slate-900 (Main window background)
COLOR_CARD = "#1E293B"     # Tailwind Slate-800 (Leg containers)
COLOR_TEXT = "#F1F5F9"     # Tailwind Slate-100 (Primary labels)
COLOR_MUTED = "#94A3B8"    # Tailwind Slate-400 (Secondary text)
COLOR_ACCENT = "#3B82F6"   # Tailwind Blue-500 (Primary buttons, slider highlights)
COLOR_ACCENT_HOVER = "#2563EB" # Tailwind Blue-600
COLOR_GREEN = "#10B981"    # Emerald-500 (Connected status)
COLOR_RED = "#EF4444"      # Red-500 (Disconnected status)
COLOR_TROUGH = "#334155"   # Slate-700 (Slider track)
COLOR_CONSOLE = "#020617"  # Slate-950 (Terminal/Console bg)

# Joint Names corresponding to 2 joints per leg in our Hexapod
JOINT_NAMES = ["Coxa (Hip Sweep)", "Femur (Thigh Lift)"]

# Hexapod Channel Layout mapping
# Leg indices: 0: LF, 1: LM, 2: LB, 3: RF, 4: RM, 5: RB
LEG_COXA_CHANNELS = [0, 2, 4, 6, 8, 10]
LEG_FEMUR_CHANNELS = [1, 3, 5, 7, 9, 11]

# Femur lift direction multipliers to account for mirrored mechanical alignment
# LF, LM, LB (Left side): +offset lifts the leg
# RF, RM, RB (Right side): -offset lifts the leg
FEMUR_LIFT_DIRS = [1, 1, 1, -1, -1, -1]

# 3D Hexapod Geometry Constants (Leg mounting angles perpendicular to the hexagonal sides)
LEG_MOUNT_ANGLES = [
    math.radians(30),    # LF (0)
    math.radians(90),    # LM (1)
    math.radians(150),   # LB (2)
    math.radians(-30),   # RF (3)
    math.radians(-90),   # RM (4)
    math.radians(-150)   # RB (5)
]

# Mounting points on body (x, y) relative to center (midpoints of the hexagon sides)
LEG_MOUNT_X = [45, 0, -45, 45, 0, -45]
LEG_MOUNT_Y = [26, 52, 26, -26, -52, -26]

# Chassis corners for rendering the hexagon plate outline
CHASSIS_CORNER_X = [60, 30, -30, -60, -30, 30]
CHASSIS_CORNER_Y = [0, 52, 52, 0, -52, -52]

# Segment lengths for 3D render
L_COXA = 20
L_FEMUR = 45  # Increased slightly to match the physical leg scale

class SpiderBotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("SpiderBot Hexapod Controller & Telemetry")
        self.root.geometry("1220x880")
        self.root.configure(bg=COLOR_BG)
        self.root.resizable(True, True)

        # Serial Connection State
        self.ser = None
        self.connected = False
        self.running = True

        # Slider Throttling State
        self.last_send_time = {}
        self.pending_sends = {}

        # Servo data (offset ranges: -45 to 45 for coxa, -90 to 45 for femur)
        self.servo_offsets = [0] * 12
        self.sliders = [None] * 12
        self.value_labels = [None] * 12

        # Automation states
        self.gait_active = False
        self.gait_thread = None
        self.sweeping = False
        self.sweep_thread = None

        # 3D Viewport State
        self.camera_yaw = math.radians(-35)
        self.camera_pitch = math.radians(65)
        self.auto_rotate = True
        self.dragging = False
        self.last_drag_x = 0
        self.last_drag_y = 0

        # Build UI layout panels
        self.create_styles()
        self.build_layout_frames()
        self.build_header()
        self.build_control_panel()
        self.build_servo_grid()
        self.build_console()
        self.build_3d_visualizer()

        # Start background port scanner & auto-select CH340 / ttyUSB0
        self.scan_ports()

        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # Start 3D Animation Loop (30 FPS)
        self.animate_3d()

    def create_styles(self):
        self.font_title = ("Helvetica", 16, "bold")
        self.font_subtitle = ("Helvetica", 10)
        self.font_header = ("Helvetica", 11, "bold")
        self.font_label = ("Helvetica", 9)
        self.font_value = ("Courier New", 10, "bold")
        self.font_console = ("Courier New", 9)

    def build_layout_frames(self):
        # Left Panel (Controls and sliders)
        self.left_panel = tk.Frame(self.root, bg=COLOR_BG)
        self.left_panel.pack(side="left", fill="both", expand=True)

        # Right Panel (3D Monitor)
        self.right_panel = tk.Frame(self.root, bg=COLOR_BG)
        self.right_panel.pack(side="right", fill="both", expand=False, padx=(10, 20), pady=20)

    def build_header(self):
        header_frame = tk.Frame(self.left_panel, bg=COLOR_BG)
        header_frame.pack(fill="x", padx=20, pady=(15, 5))

        title_lbl = tk.Label(
            header_frame, 
            text="SPIDERBOT HEXAPOD CONTROLLER", 
            fg=COLOR_TEXT, 
            bg=COLOR_BG, 
            font=self.font_title
        )
        title_lbl.pack(anchor="w")

        subtitle_lbl = tk.Label(
            header_frame, 
            text="Hexapod Config: 6 Legs | 2 Joints per Leg (Coxa/Femur) | Sweep range: -45° to +45° (Centered at 90°)", 
            fg=COLOR_MUTED, 
            bg=COLOR_BG, 
            font=self.font_subtitle
        )
        subtitle_lbl.pack(anchor="w", pady=(2, 0))

    def build_control_panel(self):
        # Control & Actions Container
        control_frame = tk.Frame(self.left_panel, bg=COLOR_BG)
        control_frame.pack(fill="x", padx=20, pady=10)

        # 1. Connection Section (Left Card)
        conn_group = tk.LabelFrame(
            control_frame, 
            text=" Connection Settings ", 
            fg=COLOR_TEXT, 
            bg=COLOR_BG,
            font=self.font_header,
            bd=1,
            relief="solid",
            highlightbackground=COLOR_CARD,
            padx=10,
            pady=10
        )
        conn_group.pack(side="left", fill="both", expand=True, padx=(0, 10))

        # Port Select Row
        tk.Label(conn_group, text="Serial Port:", fg=COLOR_MUTED, bg=COLOR_BG, font=self.font_label).grid(row=0, column=0, sticky="w", padx=2, pady=5)
        self.port_var = tk.StringVar()
        self.port_dropdown = ttk.Combobox(conn_group, textvariable=self.port_var, width=12, state="readonly")
        self.port_dropdown.grid(row=0, column=1, padx=2, pady=5)

        # Refresh Ports Button
        refresh_btn = self.create_btn(conn_group, "↻", self.scan_ports, bg="#475569", hover_bg="#64748B", width=2)
        refresh_btn.grid(row=0, column=2, padx=2)

        # Connect Button
        self.connect_btn = self.create_btn(conn_group, "Connect", self.toggle_connection, bg=COLOR_ACCENT, hover_bg=COLOR_ACCENT_HOVER, width=10)
        self.connect_btn.grid(row=0, column=3, padx=5)

        # Connection Indicator Light
        self.status_canvas = tk.Canvas(conn_group, width=15, height=15, bg=COLOR_BG, highlightthickness=0)
        self.status_canvas.grid(row=0, column=4, padx=2)
        self.status_indicator = self.status_canvas.create_oval(1, 1, 14, 14, fill=COLOR_RED, outline="")
        
        self.status_lbl = tk.Label(conn_group, text="Disconnected", fg=COLOR_RED, bg=COLOR_BG, font=self.font_label)
        self.status_lbl.grid(row=0, column=5, padx=2)

        # Manual overrides (Center All & Sweep Test)
        center_btn = self.create_btn(conn_group, "Center All (0°)", self.center_all, bg="#10B981", hover_bg="#059669", width=12)
        center_btn.grid(row=1, column=0, columnspan=3, pady=(10, 0), sticky="w")

        self.sweep_btn = self.create_btn(conn_group, "Sweep Test", self.toggle_sweep, bg="#8B5CF6", hover_bg="#7C3AED", width=12)
        self.sweep_btn.grid(row=1, column=3, columnspan=3, pady=(10, 0), padx=5, sticky="w")

        # Row 2: Sweep Speed Control
        tk.Label(conn_group, text="Sweep Speed:", fg=COLOR_MUTED, bg=COLOR_BG, font=self.font_label).grid(row=2, column=0, columnspan=2, sticky="w", padx=2, pady=(10, 0))
        self.sweep_speed_var = tk.DoubleVar(value=2.0)
        self.sweep_speed_slider = tk.Scale(
            conn_group, orient="horizontal", from_=0.5, to=5.0, resolution=0.1, showvalue=1,
            bg=COLOR_BG, fg=COLOR_TEXT, troughcolor=COLOR_TROUGH, activebackground=COLOR_ACCENT,
            highlightthickness=0, bd=0, font=self.font_label, length=120, variable=self.sweep_speed_var
        )
        self.sweep_speed_slider.grid(row=2, column=2, columnspan=4, pady=(5, 0), sticky="w")

        # 2. Tripod Gait Settings (Right Card)
        gait_group = tk.LabelFrame(
            control_frame, 
            text=" Tripod Gait Controls ", 
            fg=COLOR_TEXT, 
            bg=COLOR_BG,
            font=self.font_header,
            bd=1,
            relief="solid",
            highlightbackground=COLOR_CARD,
            padx=10,
            pady=10
        )
        gait_group.pack(side="right", fill="both", expand=True)

        # Direction Selection (6 Options)
        tk.Label(gait_group, text="Direction:", fg=COLOR_MUTED, bg=COLOR_BG, font=self.font_label).grid(row=0, column=0, sticky="w", padx=5)
        self.gait_direction_var = tk.StringVar(value="Forward")
        directions = ["Forward", "Backward", "Turn Left", "Turn Right", "Strafe Left", "Strafe Right"]
        self.gait_dir_dropdown = ttk.Combobox(gait_group, textvariable=self.gait_direction_var, values=directions, width=12, state="readonly")
        self.gait_dir_dropdown.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        # Speed (Frequency in Hz)
        tk.Label(gait_group, text="Speed:", fg=COLOR_MUTED, bg=COLOR_BG, font=self.font_label).grid(row=0, column=2, sticky="w", padx=10)
        self.gait_speed_var = tk.DoubleVar(value=1.2)
        self.gait_speed_slider = tk.Scale(
            gait_group, orient="horizontal", from_=0.5, to=2.5, resolution=0.1, showvalue=1,
            bg=COLOR_BG, fg=COLOR_TEXT, troughcolor=COLOR_TROUGH, activebackground=COLOR_ACCENT,
            highlightthickness=0, bd=0, font=self.font_label, length=80, variable=self.gait_speed_var
        )
        self.gait_speed_slider.grid(row=0, column=3, padx=2)

        # Sweep Amplitude (Coxa swing width in deg)
        tk.Label(gait_group, text="Sweep Amp:", fg=COLOR_MUTED, bg=COLOR_BG, font=self.font_label).grid(row=1, column=0, sticky="w", padx=5)
        self.gait_sweep_var = tk.DoubleVar(value=30.0)
        self.gait_sweep_slider = tk.Scale(
            gait_group, orient="horizontal", from_=10.0, to=45.0, resolution=1.0, showvalue=1,
            bg=COLOR_BG, fg=COLOR_TEXT, troughcolor=COLOR_TROUGH, activebackground=COLOR_ACCENT,
            highlightthickness=0, bd=0, font=self.font_label, length=100, variable=self.gait_sweep_var
        )
        self.gait_sweep_slider.grid(row=1, column=1, padx=5, pady=5)

        # Lift Amplitude (Femur lift height in deg)
        tk.Label(gait_group, text="Lift Amp:", fg=COLOR_MUTED, bg=COLOR_BG, font=self.font_label).grid(row=1, column=2, sticky="w", padx=10)
        self.gait_lift_var = tk.DoubleVar(value=25.0)
        self.gait_lift_slider = tk.Scale(
            gait_group, orient="horizontal", from_=10.0, to=40.0, resolution=1.0, showvalue=1,
            bg=COLOR_BG, fg=COLOR_TEXT, troughcolor=COLOR_TROUGH, activebackground=COLOR_ACCENT,
            highlightthickness=0, bd=0, font=self.font_label, length=80, variable=self.gait_lift_var
        )
        self.gait_lift_slider.grid(row=1, column=3, padx=2)

        # Enable/Disable Gait Button
        self.gait_btn = self.create_btn(gait_group, "Start Tripod Gait", self.toggle_gait, bg="#8B5CF6", hover_bg="#7C3AED", width=18)
        self.gait_btn.grid(row=0, column=4, rowspan=2, padx=15, pady=10)

    def build_servo_grid(self):
        # 6 Legs Layout arranged as 2 Columns (Left vs Right side) and 3 Rows (Front, Middle, Back)
        grid_frame = tk.Frame(self.left_panel, bg=COLOR_BG)
        grid_frame.pack(fill="both", expand=True, padx=20, pady=5)

        # Row 0: LF, RF
        # Row 1: LM, RM
        # Row 2: LB, RB
        legs_config = [
            ("LEG 1: FRONT LEFT (LF)", [0, 1], 0, 0),
            ("LEG 4: FRONT RIGHT (RF)", [6, 7], 0, 1),
            ("LEG 2: MIDDLE LEFT (LM)", [2, 3], 1, 0),
            ("LEG 5: MIDDLE RIGHT (RM)", [8, 9], 1, 1),
            ("LEG 3: BACK LEFT (LB)", [4, 5], 2, 0),
            ("LEG 6: BACK RIGHT (RB)", [10, 11], 2, 1),
        ]

        # Config grid weights
        grid_frame.rowconfigure(0, weight=1)
        grid_frame.rowconfigure(1, weight=1)
        grid_frame.rowconfigure(2, weight=1)
        grid_frame.columnconfigure(0, weight=1)
        grid_frame.columnconfigure(1, weight=1)

        for name, channels, r, c in legs_config:
            # Leg Card Container
            leg_card = tk.Frame(grid_frame, bg=COLOR_CARD, bd=1, relief="flat", highlightbackground="#334155")
            leg_card.grid(row=r, column=c, padx=6, pady=6, sticky="nsew")
            
            # Leg Name
            lbl = tk.Label(leg_card, text=name, fg=COLOR_TEXT, bg=COLOR_CARD, font=self.font_header)
            lbl.pack(anchor="w", padx=15, pady=(8, 3))

            # Separator line
            sep = tk.Frame(leg_card, height=1, bg="#334155")
            sep.pack(fill="x", padx=15, pady=(0, 6))

            # Inside Card: 2 joints/sliders (Coxa & Femur)
            for i, channel in enumerate(channels):
                joint_frame = tk.Frame(leg_card, bg=COLOR_CARD)
                joint_frame.pack(fill="x", padx=15, pady=3)

                # Slider label
                lbl_name = tk.Label(
                    joint_frame, 
                    text=f"{JOINT_NAMES[i]} [Ch {channel}]", 
                    fg=COLOR_MUTED, 
                    bg=COLOR_CARD, 
                    font=self.font_label,
                    width=18,
                    anchor="w"
                )
                lbl_name.pack(side="left")

                # Numeric Value Display
                val_lbl = tk.Label(
                    joint_frame, 
                    text="+00°", 
                    fg=COLOR_TEXT, 
                    bg=COLOR_CARD, 
                    font=self.font_value, 
                    width=5
                )

                # Slider Scale (Sweep between -45/45 for Coxa, -90/45 for Femur)
                min_val = -45 if i == 0 else -90
                slider = tk.Scale(
                    joint_frame, 
                    orient="horizontal", 
                    from_=min_val, 
                    to=45, 
                    resolution=1,
                    showvalue=0, 
                    bg=COLOR_CARD, 
                    fg=COLOR_TEXT,
                    troughcolor=COLOR_TROUGH, 
                    activebackground=COLOR_ACCENT, 
                    highlightthickness=0, 
                    bd=0,
                    command=lambda val, ch=channel: self.on_slider_move(ch, val)
                )
                slider.set(0)
                slider.pack(side="left", fill="x", expand=True, padx=8)

                # Assign index aligned sliders/labels to keep direct channel access
                self.sliders[channel] = slider
                self.value_labels[channel] = val_lbl

                # Value label placed after slider
                val_lbl.pack(side="left", padx=2)

                # Indiv Center Button
                center_joint_btn = self.create_btn(
                    joint_frame, 
                    "⌂", 
                    lambda ch=channel: self.center_single(ch), 
                    bg="#475569", 
                    hover_bg="#64748B", 
                    width=2,
                    font=("Helvetica", 8)
                )
                center_joint_btn.pack(side="right", padx=(5, 0))

    def build_console(self):
        console_frame = tk.Frame(self.left_panel, bg=COLOR_BG)
        console_frame.pack(fill="x", padx=20, pady=(5, 15))

        tk.Label(console_frame, text="Communication Monitor", fg=COLOR_MUTED, bg=COLOR_BG, font=self.font_label).pack(anchor="w", pady=(0, 2))

        self.log_text = tk.Text(
            console_frame, 
            height=5, 
            bg=COLOR_CONSOLE, 
            fg=COLOR_MUTED, 
            font=self.font_console,
            relief="solid",
            bd=1,
            highlightthickness=0,
            padx=10,
            pady=5
        )
        self.log_text.pack(fill="x")
        self.log_text.configure(state="disabled")

    def build_3d_visualizer(self):
        # 3D Visualizer Container
        vis_group = tk.LabelFrame(
            self.right_panel, 
            text=" 3D Diagnostic Telemetry ", 
            fg=COLOR_TEXT, 
            bg=COLOR_BG,
            font=self.font_header,
            bd=1,
            relief="solid",
            highlightbackground=COLOR_CARD,
            padx=15,
            pady=15
        )
        vis_group.pack(fill="both", expand=True)

        subtitle_lbl = tk.Label(
            vis_group, 
            text="Left-click & drag to rotate view", 
            fg=COLOR_MUTED, 
            bg=COLOR_BG, 
            font=self.font_label
        )
        subtitle_lbl.pack(pady=(0, 5))

        # Canvas
        self.canvas_3d = tk.Canvas(
            vis_group, 
            width=320, 
            height=400, 
            bg=COLOR_CONSOLE, 
            relief="solid", 
            bd=1,
            highlightthickness=0
        )
        self.canvas_3d.pack(fill="both", expand=True)

        # Bind Mouse Interactions
        self.canvas_3d.bind("<Button-1>", self.on_drag_start)
        self.canvas_3d.bind("<B1-Motion>", self.on_drag_move)
        self.canvas_3d.bind("<ButtonRelease-1>", self.on_drag_stop)

        # Controls Panel for Canvas
        ctrls = tk.Frame(vis_group, bg=COLOR_BG)
        ctrls.pack(fill="x", pady=(10, 0))

        # Reset Camera Button
        reset_cam_btn = self.create_btn(ctrls, "Reset View", self.reset_camera, bg="#475569", hover_bg="#64748B", width=12)
        reset_cam_btn.pack(side="left", padx=5)

        # Auto-Rotate Toggle Checkbutton
        self.auto_rotate_var = tk.BooleanVar(value=True)
        auto_cb = tk.Checkbutton(
            ctrls, 
            text="Auto-Rotate", 
            variable=self.auto_rotate_var, 
            onvalue=True, 
            offvalue=False,
            command=self.toggle_autorotate,
            bg=COLOR_BG, 
            fg=COLOR_TEXT, 
            selectcolor=COLOR_BG,
            activebackground=COLOR_BG,
            activeforeground=COLOR_TEXT,
            font=self.font_label
        )
        auto_cb.pack(side="right", padx=10)

    def create_btn(self, parent, text, command, bg=COLOR_ACCENT, fg="#FFFFFF", hover_bg=COLOR_ACCENT_HOVER, font=None, **kwargs):
        btn_font = font if font else self.font_label
        btn = tk.Button(
            parent, 
            text=text, 
            command=command, 
            relief="flat", 
            bd=0, 
            bg=bg, 
            fg=fg, 
            activebackground=hover_bg, 
            activeforeground=fg, 
            font=btn_font, 
            **kwargs
        )
        btn.bind("<Enter>", lambda e: btn.configure(bg=hover_bg))
        btn.bind("<Leave>", lambda e: btn.configure(bg=bg))
        return btn

    def scan_ports(self):
        self.log_sys("Scanning for serial ports...")
        ports = serial.tools.list_ports.comports()
        port_list = [p.device for p in ports]
        self.port_dropdown["values"] = port_list

        if port_list:
            nano_ports = [p.device for p in ports if "USB" in p.device or "CH340" in p.description or "Qinheng" in p.description]
            if nano_ports:
                self.port_var.set(nano_ports[0])
                self.log_sys(f"Auto-detected Arduino Nano on {nano_ports[0]}")
            else:
                self.port_var.set(port_list[0])
                self.log_sys(f"Selected default port: {port_list[0]}")
        else:
            self.port_var.set("")
            self.log_sys("No serial ports found. Make sure Arduino is connected.")

    def toggle_connection(self):
        if not self.connected:
            port = self.port_var.get()
            if not port:
                messagebox.showerror("Connection Error", "Please select a serial port.")
                return

            try:
                self.log_sys(f"Connecting to {port} at 115200 baud...")
                self.ser = serial.Serial(port, 115200, timeout=1.0)
                
                # Reset delay
                time.sleep(2.0)
                
                self.connected = True
                self.connect_btn.configure(text="Disconnect", bg=COLOR_RED, activebackground="#DC2626")
                self.status_canvas.itemconfig(self.status_indicator, fill=COLOR_GREEN)
                self.status_lbl.configure(text="Connected", fg=COLOR_GREEN)
                self.port_dropdown.configure(state="disabled")
                self.log_sys(f"Successfully connected to {port}!")

                # Synchronize Arduino home positions
                self.center_all()

                self.read_thread = threading.Thread(target=self.serial_reader, daemon=True)
                self.read_thread.start()

            except PermissionError:
                self.log_sys(f"ERROR: Permission denied to {port}!")
                messagebox.showerror(
                    "Permission Error", 
                    f"Permission denied to {port}.\n\n"
                    "Please run this command in your terminal, then log out and log back in:\n"
                    "sudo usermod -a -G dialout $USER\n"
                    "Or bypass temporarily via: sudo chmod 666 /dev/ttyUSB0"
                )
            except Exception as e:
                self.log_sys(f"ERROR: Could not open {port}: {str(e)}")
                messagebox.showerror("Connection Error", f"Could not connect to {port}:\n{str(e)}")
        else:
            self.disconnect()

    def disconnect(self):
        self.connected = False
        if self.gait_active:
            self.toggle_gait()
        if self.sweeping:
            self.toggle_sweep()

        if self.ser and self.ser.is_open:
            self.ser.close()
        
        self.connect_btn.configure(text="Connect", bg=COLOR_ACCENT, activebackground=COLOR_ACCENT_HOVER)
        self.status_canvas.itemconfig(self.status_indicator, fill=COLOR_RED)
        self.status_lbl.configure(text="Disconnected", fg=COLOR_RED)
        self.port_dropdown.configure(state="readonly")
        self.log_sys("Serial port disconnected.")

    def serial_reader(self):
        while self.connected and self.running:
            if self.ser and self.ser.is_open:
                try:
                    if self.ser.in_waiting > 0:
                        line = self.ser.readline().decode("utf-8", errors="ignore").strip()
                        if line:
                            self.log_arduino(line)
                except Exception as e:
                    self.log_sys(f"Connection lost: {str(e)}")
                    self.root.after(0, self.disconnect)
                    break
            time.sleep(0.01)

    def on_slider_move(self, channel, val):
        if self.gait_active or self.sweeping:
            return  # Suppress manual adjustments during automated motions

        val = int(float(val))
        if self.value_labels[channel]:
            self.value_labels[channel].configure(text=f"{val:+}°")
        self.servo_offsets[channel] = val

        absolute_angle = 90 + val

        current_time = time.time()
        if current_time - self.last_send_time.get(channel, 0) > 0.04:
            self.send_command(channel, absolute_angle)
            self.last_send_time[channel] = current_time
            if channel in self.pending_sends:
                self.root.after_cancel(self.pending_sends[channel])
                del self.pending_sends[channel]
        else:
            if channel in self.pending_sends:
                self.root.after_cancel(self.pending_sends[channel])
            
            self.pending_sends[channel] = self.root.after(
                45, lambda ch=channel, angle=absolute_angle: self.send_pending(ch, angle)
            )

    def send_pending(self, channel, angle):
        self.send_command(channel, angle)
        self.last_send_time[channel] = time.time()
        if channel in self.pending_sends:
            del self.pending_sends[channel]

    def send_command(self, channel, angle):
        cmd = f"{channel}:{angle}\n"
        if self.connected and self.ser and self.ser.is_open:
            try:
                self.ser.write(cmd.encode("utf-8"))
            except Exception as e:
                self.log_sys(f"Send failed: {str(e)}")
        else:
            self.log_sys(f"[Simulated] Channel {channel} -> {angle}° (offset: {angle-90:+}°)")

    def center_single(self, channel):
        if self.sliders[channel]:
            self.sliders[channel].set(0)
            self.on_slider_move(channel, 0)

    def center_all(self):
        self.log_sys("Centering all 12 servos to absolute 90° (offset 0°)")
        for slider in self.sliders:
            if slider:
                slider.set(0)
        for ch in range(12):
            self.on_slider_move(ch, 0)

    def toggle_gait(self):
        if not self.gait_active:
            if not self.connected:
                if not messagebox.askyesno("Simulation Mode", "Not connected to hardware. Run tripod gait in simulation mode?"):
                    return
            
            # Stop sweep if active
            if self.sweeping:
                self.toggle_sweep()

            self.gait_active = True
            self.gait_btn.configure(text="Stop Tripod Gait", bg=COLOR_RED, activebackground="#DC2626")
            self.log_sys("Tripod gait enabled.")
            
            self.gait_thread = threading.Thread(target=self.run_gait, daemon=True)
            self.gait_thread.start()
        else:
            self.gait_active = False
            self.gait_btn.configure(text="Start Tripod Gait", bg="#8B5CF6", activebackground="#7C3AED")
            self.log_sys("Tripod gait disabled. Resetting to center.")
            self.center_all()

    def run_gait(self):
        t = 0.0
        last_time = time.time()
        
        while self.gait_active and self.running:
            current_time = time.time()
            dt = current_time - last_time
            last_time = current_time
            
            # Fetch UI gait parameters
            speed = float(self.gait_speed_var.get())
            sweep_amp = float(self.gait_sweep_var.get())
            lift_amp = float(self.gait_lift_var.get())
            direction = self.gait_direction_var.get()
            
            omega = 2.0 * math.pi * speed
            t += dt
            theta = (omega * t) % (2.0 * math.pi)
            
            for leg in range(6):
                if leg in [0, 4, 2]:
                    theta_leg = theta
                else:
                    theta_leg = theta + math.pi
                
                coxa_multiplier = self.get_coxa_multiplier(leg, direction)
                lift = max(0.0, math.sin(theta_leg)) * lift_amp
                sweep = -math.cos(theta_leg) * sweep_amp * coxa_multiplier
                femur_dir = FEMUR_LIFT_DIRS[leg]
                
                coxa_angle = 90 + int(sweep)
                femur_angle = 90 + int(lift * femur_dir)
                
                coxa_ch = LEG_COXA_CHANNELS[leg]
                femur_ch = LEG_FEMUR_CHANNELS[leg]
                
                # Update local state list so 3D visualizer reads it
                self.servo_offsets[coxa_ch] = int(sweep)
                self.servo_offsets[femur_ch] = int(lift * femur_dir)

                self.send_command(coxa_ch, coxa_angle)
                time.sleep(0.0015)
                self.send_command(femur_ch, femur_angle)
                time.sleep(0.0015)
                
                self.root.after(0, lambda c=coxa_ch, ca=coxa_angle, f=femur_ch, fa=femur_angle: self.update_gait_ui(c, ca, f, fa))
            
            time.sleep(0.03)

    def update_gait_ui(self, coxa_ch, coxa_angle, femur_ch, femur_angle):
        if self.sliders[coxa_ch]:
            self.sliders[coxa_ch].set(coxa_angle - 90)
            self.value_labels[coxa_ch].configure(text=f"{coxa_angle - 90:+}°")
        if self.sliders[femur_ch]:
            self.sliders[femur_ch].set(femur_angle - 90)
            self.value_labels[femur_ch].configure(text=f"{femur_angle - 90:+}°")

    def get_coxa_multiplier(self, leg_index, direction):
        if direction == "Forward":
            return 1.0
        elif direction == "Backward":
            return -1.0
        elif direction == "Turn Left":
            return -1.0 if leg_index < 3 else 1.0
        elif direction == "Turn Right":
            return 1.0 if leg_index < 3 else -1.0
        elif direction == "Strafe Left":
            multipliers = [-1.0, -1.0, 1.0, 1.0, 1.0, -1.0]
            return multipliers[leg_index]
        elif direction == "Strafe Right":
            multipliers = [1.0, 1.0, -1.0, -1.0, -1.0, 1.0]
            return multipliers[leg_index]
        return 0.0

    def toggle_sweep(self):
        if not self.sweeping:
            if not self.connected:
                if not messagebox.askyesno("Simulation Mode", "Not connected to hardware. Run sweep test in simulation mode?"):
                    return
            
            # Stop gait if active
            if self.gait_active:
                self.toggle_gait()

            self.sweeping = True
            self.sweep_btn.configure(text="Stop Sweep", bg=COLOR_RED, activebackground="#DC2626")
            self.log_sys("Starting general sweep test (sine wave on all channels)...")
            
            self.sweep_thread = threading.Thread(target=self.run_sweep, daemon=True)
            self.sweep_thread.start()
        else:
            self.sweeping = False
            self.sweep_btn.configure(text="Sweep Test", bg="#8B5CF6", activebackground="#7C3AED")
            self.log_sys("Sweep test stopped. Resetting to center.")
            self.center_all()

    def run_sweep(self):
        t = 0.0
        dt = 0.03
        while self.sweeping and self.running:
            frequency = float(self.sweep_speed_var.get())
            for ch in range(12):
                phase_offset = (ch % 2) * (math.pi / 4) + (ch // 2) * (math.pi / 3)
                offset = int(45.0 * math.sin(t + phase_offset))
                absolute_angle = 90 + offset
                
                # Update local state list so 3D visualizer reads it
                self.servo_offsets[ch] = offset

                self.send_command(ch, absolute_angle)
                time.sleep(0.0015)  # optimized transmission rate
                
                self.root.after(0, lambda c=ch, o=offset: self.update_single_ui(c, o))
                
            t += dt * frequency  # Phase step changes with sweep speed
            time.sleep(dt)

    def update_single_ui(self, channel, offset):
        if self.sliders[channel]:
            self.sliders[channel].set(offset)
            self.value_labels[channel].configure(text=f"{offset:+}°")

    # 3D Math and Wireframe Rendering Engine
    def reset_camera(self):
        self.camera_yaw = math.radians(-35)
        self.camera_pitch = math.radians(65)
        self.draw_3d_robot()

    def toggle_autorotate(self):
        self.auto_rotate = self.auto_rotate_var.get()

    def on_drag_start(self, event):
        self.dragging = True
        self.last_drag_x = event.x
        self.last_drag_y = event.y

    def on_drag_move(self, event):
        dx = event.x - self.last_drag_x
        dy = event.y - self.last_drag_y
        
        # Adjust camera angles based on drag
        self.camera_yaw += dx * 0.007
        self.camera_pitch += dy * 0.007
        
        # Enforce pitch limits to prevent inversion
        self.camera_pitch = max(math.radians(5), min(math.radians(85), self.camera_pitch))
        
        self.last_drag_x = event.x
        self.last_drag_y = event.y
        self.draw_3d_robot()

    def on_drag_stop(self, event):
        self.dragging = False

    def project_3d(self, x, y, z):
        # 3D Coordinates (X forward, Y left, Z up)
        # Apply Yaw (rotation around Z-axis)
        cos_y, sin_y = math.cos(self.camera_yaw), math.sin(self.camera_yaw)
        x1 = x * cos_y - y * sin_y
        y1 = x * sin_y + y * cos_y
        z1 = z

        # Apply Pitch (rotation around X-axis)
        cos_p, sin_p = math.cos(self.camera_pitch), math.sin(self.camera_pitch)
        x2 = x1
        y2 = y1 * cos_p + z1 * sin_p
        z2 = y1 * sin_p - z1 * cos_p

        # Orthographic Projection with translation to center of canvas
        # Canvas dimensions are roughly 320 x 400
        cx, cy = 160, 200
        scale = 1.7  # scale factor
        
        screen_x = cx + x2 * scale
        screen_y = cy - y2 * scale  # Invert Y to match screen coords
        return screen_x, screen_y

    def draw_3d_robot(self):
        self.canvas_3d.delete("all")

        # 1. Draw diagnostic ground grid/faint reference axes
        grid_color = "#1E293B"
        grid_size = 120
        grid_steps = 4
        for i in range(-grid_steps, grid_steps + 1):
            val = i * (grid_size / grid_steps)
            x_start, y_start = self.project_3d(val, -grid_size, -40)
            x_end, y_end = self.project_3d(val, grid_size, -40)
            self.canvas_3d.create_line(x_start, y_start, x_end, y_end, fill=grid_color)
            
            x_start2, y_start2 = self.project_3d(-grid_size, val, -40)
            x_end2, y_end2 = self.project_3d(grid_size, val, -40)
            self.canvas_3d.create_line(x_start2, y_start2, x_end2, y_end2, fill=grid_color)

        # 2. Compute 3D Coordinates for Body Hexagon (Corners)
        chassis_projected = []
        for x, y in zip(CHASSIS_CORNER_X, CHASSIS_CORNER_Y):
            screen_x, screen_y = self.project_3d(x, y, 0)
            chassis_projected.append((screen_x, screen_y))

        # Draw Chassis Hexagon lines connecting corners
        for idx in range(6):
            pt1 = chassis_projected[idx]
            pt2 = chassis_projected[(idx + 1) % 6]
            self.canvas_3d.create_line(pt1[0], pt1[1], pt2[0], pt2[1], fill=COLOR_ACCENT, width=2)

        # Draw a technical center line / directional cross inside the body
        center_x, center_y = self.project_3d(0, 0, 0)
        front_x, front_y = self.project_3d(30, 0, 0)
        # Arrow pointing forward (diagnostic)
        self.canvas_3d.create_line(center_x, center_y, front_x, front_y, fill=COLOR_RED, arrow="last", width=2)

        # 3. Calculate and Draw Leg Segments (Coxa and Femur)
        for leg in range(6):
            # Base joint mounting point on chassis (midpoints of sides)
            x_b = LEG_MOUNT_X[leg]
            y_b = LEG_MOUNT_Y[leg]
            z_b = 0
            
            # Fetch active servo offsets from local cache
            coxa_offset = math.radians(self.servo_offsets[LEG_COXA_CHANNELS[leg]])
            femur_offset = math.radians(self.servo_offsets[LEG_FEMUR_CHANNELS[leg]])

            # Leg Mounting Angle
            mount_ang = LEG_MOUNT_ANGLES[leg]

            # Calculate Femur Joint End (Coxa horizontal sweep)
            theta_yaw = mount_ang + coxa_offset
            x_c = x_b + L_COXA * math.cos(theta_yaw)
            y_c = y_b + L_COXA * math.sin(theta_yaw)
            z_c = z_b

            # Calculate Foot Point End (Femur points straight down at default 90 deg)
            # Femur angle offset relative to vertical line (positive rotates leg outward/upward)
            # We map offset via FEMUR_LIFT_DIRS to handle mechanical mirroring
            theta_femur_eff = femur_offset * FEMUR_LIFT_DIRS[leg]
            
            # If default is 90 deg pointing straight down (vertical)
            # L_f_horiz (horizontal extension outward) = L_FEMUR * sin(theta_femur_eff)
            # L_f_vert (vertical extension downward) = L_FEMUR * cos(theta_femur_eff)
            L_f_horiz = L_FEMUR * math.sin(theta_femur_eff)
            L_f_vert = L_FEMUR * math.cos(theta_femur_eff)

            x_f = x_c + L_f_horiz * math.cos(theta_yaw)
            y_f = y_c + L_f_horiz * math.sin(theta_yaw)
            z_f = z_c - L_f_vert

            # Project coordinates onto screen
            screen_b = self.project_3d(x_b, y_b, z_b)
            screen_c = self.project_3d(x_c, y_c, z_c)
            screen_f = self.project_3d(x_f, y_f, z_f)

            # Determine Leg Color depending on tripod grouping
            # Tripod 1: LF(0), RM(4), LB(2) -> Green
            # Tripod 2: RF(3), LM(1), RB(5) -> Violet
            leg_color = "#10B981" if leg in [0, 4, 2] else "#A78BFA"

            # Draw Coxa Segment (Body to Coxa Joint)
            self.canvas_3d.create_line(screen_b[0], screen_b[1], screen_c[0], screen_c[1], fill="#E2E8F0", width=2)
            
            # Draw Femur Segment (Coxa Joint to Foot)
            self.canvas_3d.create_line(screen_c[0], screen_c[1], screen_f[0], screen_f[1], fill=leg_color, width=3)

            # Draw Foot Contact Point Dot
            r = 3
            self.canvas_3d.create_oval(
                screen_f[0] - r, screen_f[1] - r, 
                screen_f[0] + r, screen_f[1] + r, 
                fill=COLOR_RED, outline=""
            )

        # 4. Canvas Text Overlays
        self.canvas_3d.create_text(
            10, 15, text="LIVE TELEMETRY MONITOR", 
            fill=COLOR_TEXT, font=("Helvetica", 9, "bold"), anchor="w"
        )
        mode_str = "WALKING TRIPOD GAIT" if self.gait_active else ("SWEEP OSCILLATION" if self.sweeping else "MANUAL OVERRIDE")
        self.canvas_3d.create_text(
            10, 32, text=f"MODE: {mode_str}", 
            fill=COLOR_MUTED, font=self.font_label, anchor="w"
        )

    def animate_3d(self):
        if self.running:
            # Auto-rotate camera slowly when not dragging
            if self.auto_rotate and not self.dragging:
                self.camera_yaw += 0.006
                # Wrap angle within 2pi
                self.camera_yaw %= (2.0 * math.pi)
            
            self.draw_3d_robot()
            
            # Re-schedule at ~33 FPS (30ms sleep)
            self.root.after(30, self.animate_3d)

    def log_sys(self, message):
        self.log(f"[SYS] {message}", COLOR_MUTED)

    def log_arduino(self, message):
        self.log(f"[MCU] {message}", COLOR_GREEN if "ACK" in message else COLOR_RED)

    def log(self, text, color):
        self.root.after(0, lambda: self._write_log(text, color))

    def _write_log(self, text, color):
        self.log_text.configure(state="normal")
        timestamp = time.strftime("%H:%M:%S")
        tag_name = f"color_{color}"
        
        self.log_text.tag_config(tag_name, foreground=color)
        self.log_text.insert("end", f"[{timestamp}] ")
        self.log_text.insert("end", f"{text}\n", tag_name)
        
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def on_close(self):
        self.running = False
        self.gait_active = False
        self.sweeping = False
        if self.ser and self.ser.is_open:
            self.ser.close()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = SpiderBotGUI(root)
    root.mainloop()
