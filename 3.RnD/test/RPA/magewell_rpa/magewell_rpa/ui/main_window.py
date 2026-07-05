import tkinter as tk
from tkinter import filedialog, messagebox, Menu
from PIL import Image, ImageTk
import cv2
import os
import time
import numpy as np

from ..state import AppState
from ..core.video_source import VideoSource
from ..core.tracker import TrackingEngine
import serial.tools.list_ports
from ..core.relay_board import RelayBoardController

class MainWindow:
    def __init__(self, root, args):
        self.root = root
        self.root.title("Magewell RPA Motion & Tracking (OOP)")
        self.root.geometry("1200x800") # UI 확장을 위해 크기 증가
        
        # 상태 및 엔진 초기화
        self.state = AppState()
        self.video_source = VideoSource(self.state.source_type, self.state.source_path)
        self.tracker = TrackingEngine()
        
        # CLI 인자 처리
        if args.video:
            self.load_video_file(args.video)
        if args.template:
            self.load_template_file(args.template)
            
        # UI 초기화
        self.setup_ui()
        self.setup_menu()
        self.setup_shortcuts()
        
        # 메인 루프 시작
        self.update_frame()
        
    def setup_ui(self):
        # PanedWindow
        self.main_pane = tk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.main_pane.pack(fill=tk.BOTH, expand=True)

        self.left_frame = tk.Frame(self.main_pane)
        self.main_pane.add(self.left_frame, minsize=600, stretch="always")

        self.right_frame = tk.Frame(self.main_pane, width=250, bg="#f0f0f0")
        self.main_pane.add(self.right_frame, minsize=200, stretch="never")
        
        # Video Canvas & Scrollbars
        self.video_canvas = tk.Canvas(self.left_frame, bg="black")
        self.v_scroll = tk.Scrollbar(self.left_frame, orient=tk.VERTICAL, command=self.video_canvas.yview)
        self.h_scroll = tk.Scrollbar(self.left_frame, orient=tk.HORIZONTAL, command=self.video_canvas.xview)
        
        self.video_canvas.configure(yscrollcommand=self.v_scroll.set, xscrollcommand=self.h_scroll.set)
        
        self.left_frame.grid_rowconfigure(0, weight=1)
        self.left_frame.grid_columnconfigure(0, weight=1)
        
        self.video_canvas.grid(row=0, column=0, sticky="nsew")
        self.v_scroll.grid(row=0, column=1, sticky="ns")
        self.h_scroll.grid(row=1, column=0, sticky="ew")
        
        self.video_label = tk.Label(self.video_canvas, bg="black")
        self.canvas_window = self.video_canvas.create_window(0, 0, window=self.video_label, anchor="nw")
        self.video_label.bind("<Configure>", self.on_canvas_configure)

        # 수동 ROI 선택 (Tkinter 네이티브 드래그) 상태 및 바인딩
        # 프레임은 원본 해상도로 표시되므로 라벨 좌표 = 프레임 픽셀 좌표(1:1)
        self.roi_mode = False
        self._roi_start = None
        self._roi_preview = None
        self.video_label.bind("<ButtonPress-1>", self._on_roi_press)
        self.video_label.bind("<B1-Motion>", self._on_roi_drag)
        self.video_label.bind("<ButtonRelease-1>", self._on_roi_release)
        self.root.bind("<Escape>", self._cancel_roi)
        
        # Status Bar
        self.status_var = tk.StringVar()
        self.status_var.set("준비 (Ready)")
        self.status_bar = tk.Label(self.left_frame, textvariable=self.status_var, bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.grid(row=2, column=0, columnspan=2, sticky="ew")
        
        # Right Pane - Controls
        self._setup_right_pane()
        
    def on_canvas_configure(self, event):
        self.video_canvas.configure(scrollregion=self.video_canvas.bbox("all"))

    def _setup_right_pane(self):
        # Relay Board Control
        self._setup_relay_ui()

        # Template List
        lbl_title = tk.Label(self.right_frame, text="로드된 템플릿 목록", font=("Arial", 12, "bold"), bg="#f0f0f0")
        lbl_title.pack(pady=(10, 5))

        listbox_frame = tk.Frame(self.right_frame)
        listbox_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        scrollbar = tk.Scrollbar(listbox_frame, orient=tk.VERTICAL)
        self.template_listbox = tk.Listbox(listbox_frame, yscrollcommand=scrollbar.set, selectmode=tk.SINGLE, font=("Arial", 10))
        scrollbar.config(command=self.template_listbox.yview)
        
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.template_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Buttons
        btn_frame = tk.Frame(self.right_frame, bg="#f0f0f0")
        btn_frame.pack(fill=tk.X, padx=5, pady=10)
        
        tk.Button(btn_frame, text="선택 항목 삭제", command=self.remove_selected_template).pack(fill=tk.X, pady=2)
        tk.Button(btn_frame, text="전체 삭제", command=self.clear_all_templates).pack(fill=tk.X, pady=2)
        
        # Sliders
        self._create_slider("매칭 임계값 (Threshold)", 0.1, 1.0, 0.01, self.state.match_threshold, self.update_threshold)
        self._create_slider("탐지 주기 (Frames)", 1, 30, 1, self.state.detect_interval, self.update_interval)
        self._create_slider("마우스 감도 (Sensitivity)", 0.1, 5.0, 0.1, self.state.mouse_speed_scale, self.update_mouse_scale)

    def _setup_relay_ui(self):
        frame = tk.LabelFrame(self.right_frame, text="Relay Board Control", bg="#f0f0f0", padx=5, pady=5)
        frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Port Selection
        self.port_var = tk.StringVar()
        self.port_menu = tk.OptionMenu(frame, self.port_var, "")
        self.port_menu.config(width=15)
        self.port_menu.pack(fill=tk.X, pady=2)
        
        btn_refresh = tk.Button(frame, text="포트 새로고침", command=self.refresh_ports)
        btn_refresh.pack(fill=tk.X, pady=2)
        
        self.btn_connect = tk.Button(frame, text="연결 (Connect)", command=self.toggle_relay_connection, bg="#e0e0e0")
        self.btn_connect.pack(fill=tk.X, pady=5)
        
        self.refresh_ports()

    def refresh_ports(self):
        ports = [port.device for port in serial.tools.list_ports.comports()]
        menu = self.port_menu["menu"]
        menu.delete(0, "end")
        
        if not ports:
            self.port_var.set("")
            menu.add_command(label="No Ports", command=lambda: self.port_var.set(""))
        else:
            for port in ports:
                menu.add_command(label=port, command=lambda p=port: self.port_var.set(p))
            if not self.port_var.get() or self.port_var.get() not in ports:
                self.port_var.set(ports[0])

    def toggle_relay_connection(self):
        if self.state.relay_connected:
            # Disconnect
            if self.state.relay_controller:
                self.state.relay_controller.disconnect()
            self.state.relay_connected = False
            self.state.relay_controller = None
            self.btn_connect.config(text="연결 (Connect)", bg="#e0e0e0")
            self._update_status("릴레이 보드 연결 해제됨")
        else:
            # Connect
            port = self.port_var.get()
            if not port:
                messagebox.showerror("Error", "포트를 선택하세요.")
                return
                
            controller = RelayBoardController(port, verbose=False)
            if controller.connect():
                self.state.relay_controller = controller
                self.state.relay_connected = True
                self.btn_connect.config(text="연결 해제 (Disconnect)", bg="#a0ffa0")
                
                # 초기화: 홈(0,0)으로 이동
                controller.reset_mouse()
                self.state.current_mouse_x = 0
                self.state.current_mouse_y = 0

                # 자동 홈 원점 보정:
                # reset_mouse 는 커서를 실제 화면 (0,0) 으로 홈잉하지만, 캡처 프레임에는
                # 검은 여백/오버스캔이 있어 그 지점이 프레임 (offx, offy) 로 잡힌다.
                # target 은 프레임 좌표로 계산되므로, current 초기값을 실측 프레임 원점으로
                # 맞춰야 커서가 target 에 정확히 도달한다. (오버스캔/해상도 변화에도 자동 대응)
                origin = self._calibrate_home_origin(controller)
                if origin:
                    self.state.current_mouse_x = origin[0]
                    self.state.current_mouse_y = origin[1]
                    self._update_status(f"릴레이 보드 연결됨 ({port}) | 홈 원점 보정 {origin}")
                else:
                    self._update_status(f"릴레이 보드 연결됨 ({port}) | 원점 보정 실패(0,0 사용)")
            else:
                messagebox.showerror("Error", f"{port} 연결 실패")

    def _create_slider(self, label, min_val, max_val, res, init_val, command):
        frame = tk.Frame(self.right_frame, bg="#f0f0f0")
        frame.pack(fill=tk.X, padx=5, pady=5)
        
        tk.Label(frame, text=label, bg="#f0f0f0").pack(side=tk.TOP, anchor=tk.W)
        val_label = tk.Label(frame, text=f"{init_val}", bg="#f0f0f0")
        val_label.pack(side=tk.BOTTOM, anchor=tk.E)
        
        def on_change(val):
            command(float(val))
            val_format = f"{float(val):.2f}" if isinstance(res, float) else f"{int(float(val))}"
            val_label.config(text=val_format)

        scale = tk.Scale(frame, from_=min_val, to=max_val, resolution=res, orient=tk.HORIZONTAL, command=on_change)
        scale.set(init_val)
        scale.pack(fill=tk.X)

    def setup_menu(self):
        menu_bar = tk.Menu(self.root)
        
        # Source Menu
        source_menu = tk.Menu(menu_bar, tearoff=0)
        source_menu.add_command(label="라이브 카메라 (c)", command=self.connect_camera)
        source_menu.add_command(label="테스트 비디오 (v)", command=self.open_video_file_dialog)
        source_menu.add_separator()
        source_menu.add_command(label="종료 (q)", command=self.quit_app)
        menu_bar.add_cascade(label="소스 (Source)", menu=source_menu)

        # Tracking Menu
        track_menu = tk.Menu(menu_bar, tearoff=0)
        track_menu.add_command(label="템플릿 가져오기 (i)", command=self.open_template_file_dialog)
        track_menu.add_command(label="템플릿 초기화", command=self.clear_all_templates)
        track_menu.add_separator()
        track_menu.add_command(label="수동 ROI 설정 (r)", command=self.set_manual_roi)
        menu_bar.add_cascade(label="트래킹 (Tracking)", menu=track_menu)
        
        # Playback Menu
        play_menu = tk.Menu(menu_bar, tearoff=0)
        play_menu.add_command(label="0.5x (느리게)", command=lambda: self.set_playback_speed(0.5))
        play_menu.add_command(label="1.0x (보통)", command=lambda: self.set_playback_speed(1.0))
        play_menu.add_command(label="2.0x (빠르게)", command=lambda: self.set_playback_speed(2.0))
        play_menu.add_command(label="4.0x (매우 빠르게)", command=lambda: self.set_playback_speed(4.0))
        menu_bar.add_cascade(label="재생 (Playback)", menu=play_menu)

        self.root.config(menu=menu_bar)

    def setup_shortcuts(self):
        self.root.bind('v', lambda e: self.open_video_file_dialog())
        self.root.bind('c', lambda e: self.connect_camera())
        self.root.bind('i', lambda e: self.open_template_file_dialog())
        self.root.bind('r', lambda e: self.set_manual_roi())
        self.root.bind('q', lambda e: self.quit_app())
        self.root.bind('+', lambda e: self.increase_speed())
        self.root.bind('=', lambda e: self.increase_speed())
        self.root.bind('-', lambda e: self.decrease_speed())
        
    # --- Logic ---
    
    def update_frame(self):
        ret, frame = self.video_source.read_frame(self.state.playback_speed)
        
        if not ret or frame is None:
            # Re-try loop if camera fails or wait if file ended (handled in VideoSource logic usually)
            # 실패 시 재시도 (카메라는 천천히, 파일은 빠르게)
            delay = 500 if self.state.source_type == "CAMERA" else 100
            self.root.after(delay, self.update_frame)
            return

        self.state.frame_count += 1
        display_frame = frame.copy()
        
        # 1. Template Matching
        if self.state.templates:
            effective_interval = max(1, int(self.state.detect_interval / self.state.playback_speed))
            
            if self.state.frame_count % effective_interval == 0:
                self.state.last_detected_rects = self.tracker.match_templates(
                    frame, self.state.templates, self.state.match_threshold
                )
            
            # Draw results
            for (rect, name, score, color) in self.state.last_detected_rects:
                x, y, w, h = rect
                cv2.rectangle(display_frame, (x, y), (x + w, y + h), color, 2)
                label = f"{name} ({score:.2f}) ({x}, {y})"
                lbl_y = y - 5 if y - 5 > 10 else y + h + 15
                cv2.putText(display_frame, label, (x, lbl_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

            # 릴레이 보드 연동 마우스 이동 (가장 높은 점수의 객체 기준)
            if self.state.relay_connected and self.state.last_detected_rects:
                # 점수 기준으로 정렬 (내림차순)
                best_match = sorted(self.state.last_detected_rects, key=lambda x: x[2], reverse=True)[0]
                rect, name, score, _ = best_match
                
                # 영상 내 좌표 (rect의 x, y: 검출 박스 좌상단, UI 레이블과 동일한 좌표)
                x, y, w, h = rect

                # 좌표 변환 (Video Resolution -> Monitor Resolution)
                # 클릭 정확도를 위해 검출 박스의 '중심'을 타깃으로 삼는다
                # (커서 팁이 템플릿 중앙에 위치 -> 버튼 클릭에 적합).
                frame_h, frame_w = frame.shape[:2]
                monitor_w, monitor_h = self.state.target_monitor_size

                center_fx = x + w / 2.0
                center_fy = y + h / 2.0
                target_x = int((center_fx / frame_w) * monitor_w)
                target_y = int((center_fy / frame_h) * monitor_h)

                # 델타 계산: D = Tgt - Cur (감도 배율 적용)
                scale = self.state.mouse_speed_scale  # 감도 배율 (1.0 = 기준)
                dx = int((target_x - self.state.current_mouse_x) * scale)
                dy = int((target_y - self.state.current_mouse_y) * scale)

                # 진단 로그 (초당 ~2회로 스로틀, 폭주 방지). Y 좌표 이슈 추적용.
                if self.state.frame_count % 15 == 0:
                    print(f"[Track] frame={frame_w}x{frame_h} match={name}@({x},{y}) "
                          f"score={score:.2f} target=({target_x},{target_y}) "
                          f"cur=({int(self.state.current_mouse_x)},{int(self.state.current_mouse_y)}) "
                          f"d=({dx},{dy})", flush=True)

                # 이동 명령 전송.
                # 데드존: 미세 오차(±2px)는 무시하여 불필요한 전송/떨림 방지.
                # 프레임당 이동량을 1패킷(±127)로 제한하여 Tk 메인루프를 막지 않는다.
                # (기존 move_mouse_relative는 큰 delta를 127씩 쪼개 동기 전송+sleep 하여
                #  시각 피드백 폭주 시 UI가 얼어붙었음. 잔여 오차는 다음 프레임에서 재수렴.)
                DEADZONE = 2
                MAX_STEP = 127
                if abs(dx) > DEADZONE or abs(dy) > DEADZONE:
                    step_x = max(min(dx, MAX_STEP), -MAX_STEP)
                    step_y = max(min(dy, MAX_STEP), -MAX_STEP)
                    self.state.relay_controller.send_mouse_move(step_x, step_y, quiet=True)

                    # 실제 전송한 step만큼만 현재 위치 갱신 (다음 프레임에서 잔여 오차 재계산)
                    self.state.current_mouse_x += step_x
                    self.state.current_mouse_y += step_y

                    self._update_status(f"Mouse: ({target_x}, {target_y})")
        
        # 2. Motion Detection
        if self.state.roi_selected and self.state.roi_rect:
            x, y, w, h = self.state.roi_rect
            cv2.rectangle(display_frame, (x, y), (x + w, y + h), (0, 255, 255), 2)
            
            detected, motion_rects = self.tracker.detect_motion(frame, self.state.roi_rect)
            for mr in motion_rects:
                mx, my, mw, mh = mr
                cv2.rectangle(display_frame, (mx, my), (mx+mw, my+mh), (0, 0, 255), 2)
            
            if detected:
                cv2.putText(display_frame, "MOTION DETECTED", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

        # 3. 수동 ROI 선택 드래그 미리보기 (초록 박스)
        if self.roi_mode and self._roi_preview:
            px0, py0, px1, py1 = self._roi_preview
            cv2.rectangle(display_frame, (px0, py0), (px1, py1), (0, 255, 0), 2)

        # Render to Tkinter
        rgb_frame = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb_frame)
        tk_image = ImageTk.PhotoImage(image=pil_image)
        self.video_label.imgtk = tk_image
        self.video_label.configure(image=tk_image)
        
        delay = self.video_source.get_delay_ms(self.state.playback_speed)
        self.root.after(delay, self.update_frame)

    # --- Actions ---
    def update_threshold(self, val):
        self.state.match_threshold = float(val)

    def update_interval(self, val):
        self.state.detect_interval = int(val)

    def update_mouse_scale(self, val):
        self.state.mouse_speed_scale = float(val)

    def _update_status(self, message=None):
        """
        Builds and sets the status string with Source Info, Scan Info, Playback Speed, and Custom Message.
        """
        source_str = "라이브 카메라" if self.state.source_type == "CAMERA" else os.path.basename(str(self.state.source_path))
        scan_info = self.video_source.get_info()
        speed_str = f"{self.state.playback_speed}x"
        
        status_text = f"소스: {source_str} | 스캔: {scan_info} | 속도: {speed_str}"
        if message:
            status_text += f" | {message}"
            
        self.status_var.set(status_text)

    def set_playback_speed(self, speed):
        self.state.playback_speed = float(speed)
        self._update_status()

    def increase_speed(self):
        speeds = [0.25, 0.5, 1.0, 2.0, 4.0, 8.0]
        try:
            current_idx = speeds.index(self.state.playback_speed)
            if current_idx < len(speeds) - 1:
                self.set_playback_speed(speeds[current_idx + 1])
        except ValueError:
            self.set_playback_speed(1.0)

    def decrease_speed(self):
        speeds = [0.25, 0.5, 1.0, 2.0, 4.0, 8.0]
        try:
            current_idx = speeds.index(self.state.playback_speed)
            if current_idx > 0:
                self.set_playback_speed(speeds[current_idx - 1])
        except ValueError:
            self.set_playback_speed(1.0)
            
    def load_video_file(self, path):
        if self.video_source.reconnect("FILE", path):
            self.state.source_type = "FILE"
            self.state.source_path = path
            self.state.playback_speed = 1.0
            self._update_status()
        else:
            messagebox.showerror("Error", f"Could not open video: {path}")

    def load_template_file(self, path):
        img = cv2.imread(path)
        if img is not None:
             h, w = img.shape[:2]
             color = (np.random.randint(50, 255), np.random.randint(50, 255), np.random.randint(50, 255))
             self.state.templates.append({
                 'name': os.path.basename(path),
                 'image': img,
                 'w': w,
                 'h': h,
                 'color': color 
             })
             self.refresh_template_list()
             self._update_status(f"템플릿 추가됨: {os.path.basename(path)}")

    def open_video_file_dialog(self):
        path = filedialog.askopenfilename(filetypes=[("Video Files", "*.mp4;*.avi;*.mov;*.mkv")])
        if path:
            self.load_video_file(path)

    def connect_camera(self):
        if self.video_source.reconnect("CAMERA", 0):
            self.state.source_type = "CAMERA"
            self.state.source_path = 0
            self._update_status("라이브 카메라 연결됨")

    def open_template_file_dialog(self):
        paths = filedialog.askopenfilenames(filetypes=[("Image Files", "*.png;*.jpg;*.jpeg;*.bmp")])
        if paths:
            for path in paths:
                self.load_template_file(path)

    def refresh_template_list(self):
        self.template_listbox.delete(0, tk.END)
        for idx, t in enumerate(self.state.templates):
            self.template_listbox.insert(tk.END, f"{idx+1}. {t['name']}")

    def remove_selected_template(self):
        selection = self.template_listbox.curselection()
        if selection:
            idx = selection[0]
            removed = self.state.templates.pop(idx)
            self.refresh_template_list()
            self._update_status(f"제거됨: {removed['name']}")

    def clear_all_templates(self):
        self.state.templates.clear()
        self.refresh_template_list()
        self.state.roi_selected = False
        self.state.roi_rect = None
        self._update_status("모든 템플릿 삭제됨")

    def _read_stable_frame(self, n=4):
        """캡처에서 여러 프레임을 읽어 마지막 유효 프레임 반환."""
        f = None
        for _ in range(n):
            ret, fr = self.video_source.read_frame()
            if ret and fr is not None:
                f = fr
            time.sleep(0.02)
        return f

    def _calibrate_home_origin(self, controller):
        """홈잉된 커서의 실제 프레임 위치를 jiggle-diff 로 측정.
        (+8,+8) 이동 전후 프레임을 차분해 커서 위치를 찾고 원위치로 복귀."""
        try:
            a = self._read_stable_frame()
            if a is None:
                return None
            controller.send_mouse_move(8, 8, quiet=True)
            time.sleep(0.25)
            b = self._read_stable_frame()
            controller.send_mouse_move(-8, -8, quiet=True)  # 원위치 복귀 (순 이동 0)
            time.sleep(0.15)
            if b is None or a.shape != b.shape:
                return None
            diff = (np.abs(a.astype(int) - b.astype(int)).sum(axis=2) > 40)
            ys, xs = np.nonzero(diff)
            if len(xs) < 5:
                return None
            # 변화영역 top-left ≈ 커서 팁(홈 원점)
            return (int(xs.min()), int(ys.min()))
        except Exception as e:
            print(f"[Calibrate] 실패: {e}")
            return None

    def set_manual_roi(self):
        # Tkinter 네이티브 ROI 선택 모드 활성화.
        # (기존 cv2.selectROI 는 Tk mainloop 안에서 자체 이벤트루프를 돌려 GIL 충돌로
        #  프로세스가 강제 종료됐음 -> 영상 캔버스 드래그 방식으로 대체)
        self.roi_mode = True
        self._roi_start = None
        self._roi_preview = None
        self._update_status("수동 ROI: 영상 위에서 마우스를 드래그해 영역을 지정하세요 (ESC 취소)")

    def _on_roi_press(self, event):
        if not self.roi_mode:
            return
        self._roi_start = (event.x, event.y)
        self._roi_preview = (event.x, event.y, event.x, event.y)

    def _on_roi_drag(self, event):
        if not self.roi_mode or self._roi_start is None:
            return
        x0, y0 = self._roi_start
        self._roi_preview = (x0, y0, event.x, event.y)

    def _on_roi_release(self, event):
        if not self.roi_mode or self._roi_start is None:
            return
        x0, y0 = self._roi_start
        x1, y1 = event.x, event.y
        # 라벨 좌표 = 프레임 픽셀 좌표(1:1). (x, y, w, h) 정규화.
        rx, ry = min(x0, x1), min(y0, y1)
        rw, rh = abs(x1 - x0), abs(y1 - y0)
        self.roi_mode = False
        self._roi_start = None
        self._roi_preview = None
        if rw > 5 and rh > 5:
            self.state.roi_rect = (rx, ry, rw, rh)
            self.state.roi_selected = True
            self._update_status(f"수동 ROI 설정됨: ({rx}, {ry}, {rw}, {rh})")
        else:
            self._update_status("ROI 취소됨 (영역이 너무 작음)")

    def _cancel_roi(self, event=None):
        if self.roi_mode:
            self.roi_mode = False
            self._roi_start = None
            self._roi_preview = None
            self._update_status("ROI 선택 취소됨")

    def quit_app(self):
        self.video_source.release()
        self.root.quit()
