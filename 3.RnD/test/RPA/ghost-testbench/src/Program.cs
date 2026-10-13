// GTB-3000 Analyzer Console — GHOST 테스트용 가상 분석 장비 SW
// 대상: Windows 7 기본 .NET 3.5 (C# 3 문법만 사용), 단일 exe
// 모든 조작·상태 변화를 logs\gtb_*.csv 에 기록한다 (GHOST 실행 결과와 대조하는 정답 로그)
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Globalization;
using System.IO;
using System.Text;
using System.Threading;
using System.Windows.Forms;
using System.Runtime.InteropServices;

namespace GhostTestBench
{
    // ------------------------------------------------------------------ 설정 (난이도)
    class Settings
    {
        public double AlarmPerMin = 0.0;     // 측정 중 분당 알람(모달) 발생 기대 횟수
        public double WarnPerMin = 0.0;      // 측정 중 분당 경고(배너) 발생 기대 횟수
        public int DelayMs = 0;              // 버튼 동작 응답 지연 (느린 장비 SW 흉내)
        public int FreezePct = 0;            // Start 시 화면 멈춤 확률(%)
        public int FreezeSec = 5;            // 멈춤 시간
        public bool RandomPos = false;       // 시작 시 창 위치 무작위
        public bool SmallFont = false;       // 작은 글꼴
        public double TimeScale = 1.0;       // 측정 시간 배율 (0.5 = 절반)
        public int Seed = 0;                 // 0 이면 시각 기반
        public string Style = "native";
        public int Tab = 0;                       // 시작 탭 (0 Recipe, 1 Run, 2 Results, 3 Alarm, 4 Settings)
        public string AutoUser = "";             // 지정 시 로그인 창 생략 (무인 시작·화면 확인용)      // native(OS 기본) | classic(고전 입체) | flat(Win10/11 평면) | dark

        public static Settings FromArgs(string[] args)
        {
            Settings s = new Settings();
            foreach (string raw in args)
            {
                string a = raw.TrimStart('/', '-');
                string k = a, v = "";
                int eq = a.IndexOf('=');
                if (eq > 0) { k = a.Substring(0, eq); v = a.Substring(eq + 1); }
                k = k.ToLowerInvariant();
                try
                {
                    if (k == "alarm") s.AlarmPerMin = double.Parse(v, CultureInfo.InvariantCulture);
                    else if (k == "warn") s.WarnPerMin = double.Parse(v, CultureInfo.InvariantCulture);
                    else if (k == "delay") s.DelayMs = int.Parse(v);
                    else if (k == "freeze") s.FreezePct = int.Parse(v);
                    else if (k == "freezesec") s.FreezeSec = int.Parse(v);
                    else if (k == "randompos") s.RandomPos = true;
                    else if (k == "smallfont") s.SmallFont = true;
                    else if (k == "timescale") s.TimeScale = double.Parse(v, CultureInfo.InvariantCulture);
                    else if (k == "seed") s.Seed = int.Parse(v);
                    else if (k == "style") s.Style = v.ToLowerInvariant();
                    else if (k == "user") s.AutoUser = v;
                    else if (k == "tab") s.Tab = int.Parse(v);
                }
                catch (Exception) { }
            }
            return s;
        }

        public override string ToString()
        {
            return string.Format(CultureInfo.InvariantCulture,
                "alarm={0};warn={1};delay={2};freeze={3}%/{4}s;randompos={5};smallfont={6};timescale={7};seed={8};style={9}",
                AlarmPerMin, WarnPerMin, DelayMs, FreezePct, FreezeSec, RandomPos, SmallFont, TimeScale, Seed, Style);
        }
    }

    // ------------------------------------------------------------------ 키 입력 기록 (Keyboard 탭)
    // 앱 전체의 WM_KEYDOWN / WM_SYSKEYDOWN 을 가로채 가상키·스캔코드·확장키를 그대로 기록한다 (컨트롤이 먹는 키 포함)
    class KeyRecorder : IMessageFilter
    {
        public MainForm Owner;
        public bool PreFilterMessage(ref Message m)
        {
            if (m.Msg == 0x100 || m.Msg == 0x104)
            {
                long lp = m.LParam.ToInt64();
                bool repeat = ((lp >> 30) & 1) == 1;
                if (!repeat)
                    Owner.OnRawKey((int)(m.WParam.ToInt64() & 0xFF), (int)((lp >> 16) & 0xFF), (int)((lp >> 24) & 1), m.Msg == 0x104);
            }
            return false;
        }
    }

    // ------------------------------------------------------------------ 웨이퍼 맵 (글자 없는 그림 요소)
    // 13 x 13 격자, 원 밖 칸은 없음. 위에 열 글자 A~M, 왼쪽에 행 숫자 1~13. 칸을 누르면 선택 표시 + 이벤트
    class WaferMap : Control
    {
        public delegate void DieHandler(string die);
        public event DieHandler DieClicked;
        const int N = 13, Cell = 26, Left0 = 40, Top0 = 40;
        string selected = "";

        public WaferMap() { DoubleBuffered = true; BackColor = Color.White; }

        static string DieName(int c, int r) { return ((char)('A' + c)).ToString() + (r + 1); }

        bool OnWafer(int c, int r)
        {
            double cx = (c + 0.5) - N / 2.0, cy = (r + 0.5) - N / 2.0;
            return cx * cx + cy * cy <= (N / 2.0) * (N / 2.0) - 0.5;
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            Graphics g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            using (Font f = new Font("Consolas", 10f, FontStyle.Bold))
            {
                for (int c = 0; c < N; c++) g.DrawString(((char)('A' + c)).ToString(), f, Brushes.Black, Left0 + c * Cell + 8, 14);
                for (int r = 0; r < N; r++) g.DrawString((r + 1).ToString(), f, Brushes.Black, 6, Top0 + r * Cell + 5);
            }
            g.DrawEllipse(Pens.Gray, Left0 - 4, Top0 - 4, N * Cell + 8, N * Cell + 8);
            for (int c = 0; c < N; c++)
                for (int r = 0; r < N; r++)
                {
                    if (!OnWafer(c, r)) continue;
                    Rectangle rc = new Rectangle(Left0 + c * Cell + 1, Top0 + r * Cell + 1, Cell - 2, Cell - 2);
                    bool sel = DieName(c, r) == selected;
                    int k = (c * 7 + r * 13) % 10;                       // 측정값 색 (녹~황)
                    using (Brush b = new SolidBrush(sel ? Color.FromArgb(220, 40, 40) : Color.FromArgb(80 + k * 12, 170, 90)))
                        g.FillRectangle(b, rc);
                }
        }

        protected override void OnMouseClick(MouseEventArgs e)
        {
            int c = (e.X - Left0) / Cell, r = (e.Y - Top0) / Cell;
            if (e.X < Left0 || e.Y < Top0 || c >= N || r >= N || !OnWafer(c, r)) return;
            selected = DieName(c, r);
            Invalidate();
            if (DieClicked != null) DieClicked(selected);
        }
    }

    // ------------------------------------------------------------------ 정답 로그
    static class TruthLog
    {
        static StreamWriter w;
        public static string PathName = "";

        public static void Open()
        {
            try
            {
                string dir = Path.Combine(Path.GetDirectoryName(Application.ExecutablePath), "logs");
                Directory.CreateDirectory(dir);
                PathName = Path.Combine(dir, "gtb_" + DateTime.Now.ToString("yyyyMMdd_HHmmss") + ".csv");
                w = new StreamWriter(PathName, true, new UTF8Encoding(true));
                w.WriteLine("time,event,detail");
                w.Flush();
            }
            catch (Exception) { w = null; }
        }

        public static void Write(string ev, string detail)
        {
            if (w == null) return;
            string d = (detail ?? "").Replace("\"", "'");
            lock (typeof(TruthLog))
            {
                w.WriteLine(string.Format("{0},{1},\"{2}\"", DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss.fff"), ev, d));
                w.Flush();
            }
        }
    }

    static class Program
    {
        [STAThread]
        static void Main(string[] args)
        {
            Settings s = Settings.FromArgs(args);
            if (s.Style != "classic") Application.EnableVisualStyles();   // classic: 고전 회색 입체 컨트롤
            Application.SetCompatibleTextRenderingDefault(false);
            Program.Style = s.Style;
            TruthLog.Open();
            TruthLog.Write("app_start", s.ToString());
            if (s.AutoUser.Length > 0)
            {
                TruthLog.Write("login_auto", s.AutoUser);
                Application.Run(new MainForm(s, s.AutoUser));
                TruthLog.Write("app_exit", "");
                return;
            }
            using (LoginForm lf = new LoginForm())
            {
                if (lf.ShowDialog() != DialogResult.OK)
                {
                    TruthLog.Write("app_exit", "login_cancel");
                    return;
                }
                Application.Run(new MainForm(s, lf.UserName));
            }
            TruthLog.Write("app_exit", "");
        }

        public static string Style = "native";

        public static Font UiFont(bool small)
        {
            return new Font("Malgun Gothic", small ? 8f : 9.5f);
        }

        // 스타일 흉내: flat = Windows 10/11 평면, dark = 다크 테마 (native/classic 은 그대로)
        public static void ApplyStyle(Control root)
        {
            if (Style != "flat" && Style != "dark") return;
            bool dark = Style == "dark";
            Color bg = dark ? Color.FromArgb(32, 32, 32) : Color.FromArgb(243, 243, 243);
            Color panel = dark ? Color.FromArgb(45, 45, 45) : Color.White;
            Color fg = dark ? Color.FromArgb(235, 235, 235) : Color.FromArgb(25, 25, 25);
            Color accent = Color.FromArgb(0, 103, 192);
            Walk(root, bg, panel, fg, accent, dark);
        }

        static void Walk(Control c, Color bg, Color panel, Color fg, Color accent, bool dark)
        {
            if (c is Button)
            {
                Button b = (Button)c;
                b.FlatStyle = FlatStyle.Flat;
                b.FlatAppearance.BorderColor = dark ? Color.FromArgb(90, 90, 90) : Color.FromArgb(200, 200, 200);
                bool colored = b.BackColor != SystemColors.Control;
                if (dark || !colored) b.BackColor = panel;
                b.ForeColor = fg;
            }
            else if (c is TextBox || c is NumericUpDown || c is ListBox || c is ListView)
            {
                c.BackColor = panel; c.ForeColor = fg;
                if (c is TextBox) ((TextBox)c).BorderStyle = BorderStyle.FixedSingle;
                if (c is ListBox) ((ListBox)c).BorderStyle = BorderStyle.FixedSingle;
            }
            else if (c is ComboBox) { ((ComboBox)c).FlatStyle = FlatStyle.Flat; c.BackColor = panel; c.ForeColor = fg; }
            else if (c is CheckBox) { ((CheckBox)c).FlatStyle = FlatStyle.Flat; c.ForeColor = fg; }
            else if (c is DataGridView)
            {
                DataGridView g = (DataGridView)c;
                g.BackgroundColor = panel; g.BorderStyle = BorderStyle.None; g.EnableHeadersVisualStyles = false;
                g.DefaultCellStyle.BackColor = panel; g.DefaultCellStyle.ForeColor = fg;
                g.DefaultCellStyle.SelectionBackColor = accent; g.DefaultCellStyle.SelectionForeColor = Color.White;
                g.ColumnHeadersDefaultCellStyle.BackColor = dark ? Color.FromArgb(60, 60, 60) : Color.FromArgb(230, 230, 230);
                g.ColumnHeadersDefaultCellStyle.ForeColor = fg;
                g.GridColor = dark ? Color.FromArgb(70, 70, 70) : Color.FromArgb(225, 225, 225);
            }
            else if (c is GroupBox || c is TabPage || c is Form)
            {
                c.BackColor = bg; c.ForeColor = fg;
            }
            else if (c is Label)
            {
                if (c.ForeColor == SystemColors.ControlText) c.ForeColor = fg;
            }
            else if (c is ToolStrip)
            {
                ToolStrip t = (ToolStrip)c;
                t.RenderMode = ToolStripRenderMode.System;
                t.BackColor = dark ? Color.FromArgb(40, 40, 40) : Color.White; t.ForeColor = fg;
            }
            foreach (Control k in c.Controls) Walk(k, bg, panel, fg, accent, dark);
        }
    }

    // ------------------------------------------------------------------ 로그인
    class LoginForm : Form
    {
        TextBox user = new TextBox(), pw = new TextBox();
        public string UserName = "";

        public LoginForm()
        {
            Text = "GTB-3000 Login";
            Font = Program.UiFont(false);
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false; MinimizeBox = false;
            StartPosition = FormStartPosition.CenterScreen;
            ClientSize = new Size(380, 210);

            Label title = new Label();
            title.Text = "GTB-3000 Analyzer Console";
            title.Font = new Font("Malgun Gothic", 13f, FontStyle.Bold);
            title.ForeColor = Color.FromArgb(30, 60, 120);
            title.SetBounds(20, 15, 340, 30);
            Label l1 = new Label(); l1.Text = "사용자 ID"; l1.SetBounds(30, 62, 90, 22);
            Label l2 = new Label(); l2.Text = "Password"; l2.SetBounds(30, 97, 90, 22);
            user.SetBounds(125, 60, 220, 24);
            pw.SetBounds(125, 95, 220, 24);
            pw.UseSystemPasswordChar = true;
            Button ok = new Button(); ok.Text = "Login"; ok.SetBounds(125, 145, 100, 32);
            Button cancel = new Button(); cancel.Text = "Cancel"; cancel.SetBounds(245, 145, 100, 32);
            ok.Click += new EventHandler(OnLogin);
            cancel.Click += delegate { DialogResult = DialogResult.Cancel; };
            AcceptButton = ok; CancelButton = cancel;
            Controls.AddRange(new Control[] { title, l1, l2, user, pw, ok, cancel });
            Program.ApplyStyle(this);
        }

        void OnLogin(object sender, EventArgs e)
        {
            string u = user.Text.Trim();
            bool okUser = (u == "operator" && pw.Text == "1234") || (u == "engineer" && pw.Text == "5678");
            if (!okUser)
            {
                TruthLog.Write("login_fail", u);
                MessageBox.Show(this, "ID 또는 비밀번호가 올바르지 않습니다.", "로그인 실패", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                pw.Text = ""; pw.Focus();
                return;
            }
            UserName = u;
            TruthLog.Write("login", u);
            DialogResult = DialogResult.OK;
        }
    }

    // ------------------------------------------------------------------ 상태 램프
    class Lamp : Control
    {
        public Color OnColor;
        bool on;
        public bool On { get { return on; } set { if (on != value) { on = value; Invalidate(); } } }

        public Lamp(string text, Color c)
        {
            Text = text; OnColor = c; Size = new Size(110, 44);
            DoubleBuffered = true;
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            Graphics g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            Color fill = on ? OnColor : Color.FromArgb(70, 70, 70);
            using (SolidBrush b = new SolidBrush(fill)) g.FillEllipse(b, 4, 6, 30, 30);
            using (Pen p = new Pen(Color.FromArgb(40, 40, 40), 2)) g.DrawEllipse(p, 4, 6, 30, 30);
            using (SolidBrush tb = new SolidBrush(ForeColor)) g.DrawString(Text, Font, tb, 40, 12);
        }
    }

    // ------------------------------------------------------------------ 7세그먼트 표시창
    class SegmentDisplay : Control
    {
        string value = "0000.00";
        public string Value { get { return value; } set { if (this.value != value) { this.value = value; Invalidate(); } } }
        static readonly Dictionary<char, string> Seg = new Dictionary<char, string>();

        static SegmentDisplay()
        {
            Seg['0'] = "abcdef"; Seg['1'] = "bc"; Seg['2'] = "abged"; Seg['3'] = "abgcd"; Seg['4'] = "fgbc";
            Seg['5'] = "afgcd"; Seg['6'] = "afgedc"; Seg['7'] = "abc"; Seg['8'] = "abcdefg"; Seg['9'] = "abcdfg";
            Seg['-'] = "g"; Seg[' '] = "";
        }

        public SegmentDisplay() { DoubleBuffered = true; BackColor = Color.Black; Size = new Size(460, 120); }

        protected override void OnPaint(PaintEventArgs e)
        {
            Graphics g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.Clear(BackColor);
            float dw = 46, dh = 84, x = 16, y = (Height - dh) / 2f, t = 9;
            using (Pen on = new Pen(Color.FromArgb(60, 255, 90), t))
            using (Pen off = new Pen(Color.FromArgb(18, 40, 22), t))
            using (SolidBrush dot = new SolidBrush(Color.FromArgb(60, 255, 90)))
            {
                on.StartCap = on.EndCap = LineCap.Round;
                off.StartCap = off.EndCap = LineCap.Round;
                foreach (char c in value)
                {
                    if (c == '.')
                    {
                        g.FillEllipse(dot, x - 4, y + dh - 6, 10, 10);
                        x += 14;
                        continue;
                    }
                    string segs = Seg.ContainsKey(c) ? Seg[c] : "";
                    float l = x, r = x + dw - 14, top = y, mid = y + dh / 2, bot = y + dh;
                    DrawSeg(g, segs.IndexOf('a') >= 0 ? on : off, l + 4, top, r - 4, top);
                    DrawSeg(g, segs.IndexOf('b') >= 0 ? on : off, r, top + 4, r, mid - 4);
                    DrawSeg(g, segs.IndexOf('c') >= 0 ? on : off, r, mid + 4, r, bot - 4);
                    DrawSeg(g, segs.IndexOf('d') >= 0 ? on : off, l + 4, bot, r - 4, bot);
                    DrawSeg(g, segs.IndexOf('e') >= 0 ? on : off, l, mid + 4, l, bot - 4);
                    DrawSeg(g, segs.IndexOf('f') >= 0 ? on : off, l, top + 4, l, mid - 4);
                    DrawSeg(g, segs.IndexOf('g') >= 0 ? on : off, l + 4, mid, r - 4, mid);
                    x += dw + 6;
                }
            }
        }

        static void DrawSeg(Graphics g, Pen p, float x1, float y1, float x2, float y2) { g.DrawLine(p, x1, y1, x2, y2); }
    }

    // ------------------------------------------------------------------ 알람 창
    class AlarmForm : Form
    {
        public bool Abort;

        public AlarmForm(string code, string message)
        {
            Text = "ALARM " + code;
            Font = Program.UiFont(false);
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false; MinimizeBox = false; ControlBox = false;
            StartPosition = FormStartPosition.CenterParent;
            ClientSize = new Size(440, 210);
            BackColor = Color.White;

            Panel head = new Panel(); head.BackColor = Color.FromArgb(200, 30, 30); head.SetBounds(0, 0, 440, 46);
            Label ht = new Label(); ht.Text = "⚠  ALARM  " + code; ht.ForeColor = Color.White;
            ht.Font = new Font("Malgun Gothic", 14f, FontStyle.Bold); ht.SetBounds(14, 8, 400, 30);
            head.Controls.Add(ht);
            Label msg = new Label(); msg.Text = message; msg.SetBounds(20, 62, 400, 60);
            msg.Font = new Font("Malgun Gothic", 10.5f);
            Button ack = new Button(); ack.Text = "확인 (Acknowledge)"; ack.SetBounds(70, 140, 150, 38);
            Button abort = new Button(); abort.Text = "측정 중단 (Abort)"; abort.SetBounds(235, 140, 150, 38);
            ack.Click += delegate { DialogResult = DialogResult.OK; };
            abort.Click += delegate { Abort = true; DialogResult = DialogResult.Abort; };
            Controls.AddRange(new Control[] { head, msg, ack, abort });
            Program.ApplyStyle(this);
            head.BackColor = Color.FromArgb(200, 30, 30);
        }
    }

    // ------------------------------------------------------------------ 메인
    class Recipe
    {
        public string Id, Name, Method, Unit;
        public int Duration;
        public double Base, SpecLo, SpecHi;
    }

    class MainForm : Form
    {
        readonly Settings cfg;
        readonly string user;
        Random rnd;
        readonly List<Recipe> recipes = new List<Recipe>();

        TabControl tabs = new TabControl();
        DataGridView recipeGrid = new DataGridView(), resultGrid = new DataGridView();
        ListView alarmList = new ListView();
        TextBox lotBox = new TextBox();
        ComboBox sampleBox = new ComboBox();
        NumericUpDown tempBox = new NumericUpDown(), repeatBox = new NumericUpDown();
        CheckBox autoCal = new CheckBox(), saveRaw = new CheckBox();
        Button loadBtn = new Button(), applyBtn = new Button();
        Label loadedLabel = new Label();

        Label runRecipe = new Label(), runLot = new Label(), runSample = new Label(), runCycle = new Label();
        Lamp lampIdle, lampRun, lampWarn, lampAlarm;
        SegmentDisplay seg = new SegmentDisplay();
        Label unitLabel = new Label(), progressLabel = new Label(), warnBanner = new Label(), busyLabel = new Label();
        ProgressBar progress = new ProgressBar();
        Button startBtn = new Button(), pauseBtn = new Button(), stopBtn = new Button();
        ListBox msgList = new ListBox();
        ToolStripStatusLabel stUser = new ToolStripStatusLabel(), stState = new ToolStripStatusLabel(),
                             stRecipe = new ToolStripStatusLabel(), stClock = new ToolStripStatusLabel();
        NumericUpDown setAlarm = new NumericUpDown(), setWarn = new NumericUpDown(), setDelay = new NumericUpDown(),
                      setFreeze = new NumericUpDown(), setScale = new NumericUpDown();
        CheckBox setSmall = new CheckBox();

        System.Windows.Forms.Timer tick = new System.Windows.Forms.Timer();
        System.Windows.Forms.Timer uiTimer = new System.Windows.Forms.Timer();
        // Keyboard 탭
        [DllImport("user32.dll")] static extern short GetKeyState(int vk);
        TabPage keyTab;
        Label keyLast = new Label(), keyHeld = new Label(), keyCount = new Label(), clipLabel = new Label();
        TextBox keyBox = new TextBox(), copySrc = new TextBox(), pasteDst = new TextBox();
        ListBox keyHist = new ListBox();
        int keyN, keyK;
        // Complex UI 탭
        TabPage cxTab;
        Label cxLast = new Label(), gainLabel = new Label();
        ComboBox chamberBox = new ComboBox();
        TreeView recipeTree = new TreeView();
        ListBox slotList = new ListBox();
        TrackBar gainBar = new TrackBar();
        DataGridView waferGrid = new DataGridView();
        WaferMap waferMap = new WaferMap();
        Button hiddenBtn = new Button();
        DateTime hoverUntil;   // 창 이동 후 화면 위치 다시 기록 (지연)
        ToolStrip toolBar;
        Recipe loaded;
        string state = "IDLE";          // IDLE / RUN / PAUSE / ALARM
        double elapsed, duration;
        int cycle, cycles;
        double sum; int samples;
        bool paramsDirty, inAlarm;
        DateTime lastTick, warnUntil;

        public MainForm(Settings s, string userName)
        {
            cfg = s; user = userName;
            rnd = new Random(cfg.Seed != 0 ? cfg.Seed : Environment.TickCount);
            BuildRecipes();
            Text = "GTB-3000 Analyzer Console  v2.4.1   [GHOST Test Bench]";
            Font = Program.UiFont(cfg.SmallFont);
            ClientSize = new Size(1380, 840);
            MinimumSize = new Size(1100, 700);
            if (cfg.RandomPos)
            {
                Rectangle wa = Screen.PrimaryScreen.WorkingArea;
                StartPosition = FormStartPosition.Manual;
                Location = new Point(wa.Left + rnd.Next(0, Math.Max(1, wa.Width - Width)), wa.Top + rnd.Next(0, Math.Max(1, wa.Height - Height)));
            }
            else StartPosition = FormStartPosition.CenterScreen;

            BuildMenu();
            BuildStatus();
            tabs.Dock = DockStyle.Fill;
            tabs.TabPages.Add(BuildRecipeTab());
            tabs.TabPages.Add(BuildRunTab());
            tabs.TabPages.Add(BuildResultTab());
            tabs.TabPages.Add(BuildAlarmTab());
            tabs.TabPages.Add(BuildSettingsTab());
            tabs.TabPages.Add(BuildKeyboardTab());
            tabs.TabPages.Add(BuildComplexTab());
            KeyRecorder kr = new KeyRecorder(); kr.Owner = this;
            Application.AddMessageFilter(kr);
            tabs.SelectedIndexChanged += delegate { TruthLog.Write("tab", tabs.SelectedTab.Text); DumpUiLater("tab"); };
            uiTimer.Interval = 600;
            uiTimer.Tick += delegate { uiTimer.Stop(); DumpUi(uiReason); };
            Shown += delegate { DumpUiLater("shown"); };
            Move += delegate { DumpUiLater("move"); };
            Resize += delegate { DumpUiLater("resize"); };
            recipeGrid.Scroll += delegate { DumpUiLater("scroll"); };
            Controls.Add(tabs);
            tabs.BringToFront();

            tick.Interval = 200;
            tick.Tick += new EventHandler(OnTick);
            tick.Tick += delegate { KeyTabTick(); };
            tick.Tick += delegate
            {
                if (hiddenBtn.Visible && DateTime.Now > hoverUntil && !hiddenBtn.Parent.ClientRectangle.Contains(hiddenBtn.Parent.PointToClient(Cursor.Position)))
                    hiddenBtn.Visible = false;
            };
            tick.Start();
            lastTick = DateTime.Now;
            SetState("IDLE");
            Log("시스템 준비 완료 (System ready)");
            FormClosing += new FormClosingEventHandler(OnClosing);
            Program.ApplyStyle(this);
            if (Program.Style == "dark") { seg.BackColor = Color.Black; warnBanner.BackColor = Color.FromArgb(120, 90, 10); warnBanner.ForeColor = Color.White; }
            if (cfg.Tab > 0 && cfg.Tab < tabs.TabCount) tabs.SelectedIndex = cfg.Tab;
            if (Program.Style != "native") Text += "  (style: " + Program.Style + ")";
        }

        // ---------------------------------------------------------------- 화면 요소 위치 (인식률 측정용 정답)
        // 보이는 메뉴·툴바·탭·컨트롤·표 행의 화면 좌표를 정답 로그에 남긴다. GHOST 가 찾은 위치와 비교한다.
        string uiReason = "";
        void DumpUiLater(string reason) { uiReason = reason; uiTimer.Stop(); uiTimer.Start(); }

        static string R(Rectangle r) { return string.Format("{0} {1} {2} {3}", r.X, r.Y, r.Width, r.Height); }

        void Ui(string kind, Rectangle screen, string text, bool enabled)
        {
            if (screen.Width <= 0 || screen.Height <= 0) return;
            TruthLog.Write("ui", string.Format("kind={0};enabled={1};rect={2};text={3}", kind, enabled ? 1 : 0, R(screen),
                (text ?? "").Replace("\r", " ").Replace("\n", " ")));
        }

        void DumpUi(string reason)
        {
            if (!IsHandleCreated || WindowState == FormWindowState.Minimized) return;
            TruthLog.Write("ui_begin", string.Format("reason={0};tab={1};client={2}", reason, tabs.SelectedTab.Text, R(RectangleToScreen(ClientRectangle))));
            if (MainMenuStrip != null)
                foreach (ToolStripItem it in MainMenuStrip.Items)
                    Ui("menu", MainMenuStrip.RectangleToScreen(it.Bounds), it.Text, it.Enabled);
            if (toolBar != null)
                foreach (ToolStripItem it in toolBar.Items)
                    if (!(it is ToolStripSeparator)) Ui("toolbar", toolBar.RectangleToScreen(it.Bounds), it.Text, it.Enabled);
            for (int i = 0; i < tabs.TabCount; i++)
                Ui("tab", tabs.RectangleToScreen(tabs.GetTabRect(i)), tabs.TabPages[i].Text, true);
            Walk(tabs.SelectedTab);
            if (tabs.SelectedTab.Controls.Contains(recipeGrid))
                for (int i = 0; i < recipeGrid.Rows.Count; i++)
                {
                    Rectangle rr = recipeGrid.GetRowDisplayRectangle(i, true);
                    if (rr.Height > 0) Ui(recipeGrid.Rows[i].Selected ? "row_selected" : "row", recipeGrid.RectangleToScreen(rr),
                        (string)recipeGrid.Rows[i].Cells[0].Value + " " + recipeGrid.Rows[i].Cells[1].Value, true);
                }
            TruthLog.Write("ui_end", reason);
        }

        void Walk(Control parent)
        {
            foreach (Control c in parent.Controls)
            {
                if (!c.Visible) continue;
                Rectangle sr = parent.RectangleToScreen(c.Bounds);
                string kind = c.GetType().Name;
                string text = c is SegmentDisplay ? ((SegmentDisplay)c).Value : c.Text;
                if (c is ComboBox || c is NumericUpDown || c is DataGridView || c is ListView || c is ListBox)
                { Ui(kind, sr, text, c.Enabled); continue; }
                Ui(kind, sr, text, c.Enabled);
                if (c.Controls.Count > 0) Walk(c);
            }
        }

        void BuildRecipes()
        {
            string[] methods = { "XRF", "TEM", "SEM-CD", "Ellipsometry", "Particle" };
            string[] names = { "산화막 두께 측정", "Gate CD 선폭", "파티클 카운트", "금속 오염 분석", "단면 TEM 분석", "Poly 두께", "Via 저항 확인", "Overlay 측정" };
            string[] units = { "nm", "nm", "ea", "ppb", "nm", "nm", "Ω", "nm" };
            double[] bases = { 120, 45, 30, 5, 80, 200, 12, 3 };
            Random r = new Random(7);                      // 레시피 목록은 항상 같게
            for (int i = 1; i <= 30; i++)
            {
                int k = (i * 5 + 3) % names.Length;
                Recipe rc = new Recipe();
                rc.Id = string.Format("RCP-{0:000}", i);
                rc.Name = names[k] + (i % 3 == 0 ? " (Long)" : "");
                rc.Method = methods[i % methods.Length];
                rc.Unit = units[k];
                rc.Duration = 8 + r.Next(0, 18) + (i % 3 == 0 ? 10 : 0);
                rc.Base = bases[k] * (0.9 + r.NextDouble() * 0.2);
                rc.SpecLo = rc.Base * 0.95; rc.SpecHi = rc.Base * 1.05;
                recipes.Add(rc);
            }
        }

        // ---------------------------------------------------------------- 메뉴·툴바·상태줄
        void BuildMenu()
        {
            MenuStrip ms = new MenuStrip();
            ToolStripMenuItem file = new ToolStripMenuItem("File");
            file.DropDownItems.Add("결과 내보내기 (Export Results)...", null, delegate { ExportResults(); });
            file.DropDownItems.Add(new ToolStripSeparator());
            file.DropDownItems.Add("종료 (Exit)", null, delegate { Close(); });
            ToolStripMenuItem rcp = new ToolStripMenuItem("Recipe");
            rcp.DropDownItems.Add("레시피 화면 (Recipe List)", null, delegate { tabs.SelectedIndex = 0; });
            rcp.DropDownItems.Add("선택 레시피 불러오기 (Load Selected)", null, delegate { LoadSelected(); });
            ToolStripMenuItem run = new ToolStripMenuItem("Run");
            run.DropDownItems.Add("측정 시작 (Start)", null, delegate { Delayed("start", StartRun); });
            run.DropDownItems.Add("일시 정지 (Pause/Resume)", null, delegate { Delayed("pause", TogglePause); });
            run.DropDownItems.Add("측정 정지 (Stop)", null, delegate { StopRun(true); });
            ToolStripMenuItem tools = new ToolStripMenuItem("Tools");
            tools.DropDownItems.Add("설정 (Settings)", null, delegate { tabs.SelectedIndex = 4; });
            tools.DropDownItems.Add("알람 기록 (Alarm Log)", null, delegate { tabs.SelectedIndex = 3; });
            ToolStripMenuItem help = new ToolStripMenuItem("Help");
            help.DropDownItems.Add("정보 (About)", null, delegate
            {
                TruthLog.Write("about", "");
                MessageBox.Show(this, "GTB-3000 Analyzer Console v2.4.1\nGHOST 테스트용 가상 분석 장비 SW\n\n정답 로그: " + TruthLog.PathName,
                    "About GTB-3000", MessageBoxButtons.OK, MessageBoxIcon.Information);
            });
            ToolStripMenuItem ana = new ToolStripMenuItem("Analysis");
            ToolStripMenuItem wafer = new ToolStripMenuItem("Wafer");
            ToolStripMenuItem mapExp = new ToolStripMenuItem("Map Export");
            mapExp.DropDownItems.Add("CSV", null, delegate { Evt("menu", "Analysis>Wafer>Map Export>CSV"); });
            mapExp.DropDownItems.Add("PNG", null, delegate { Evt("menu", "Analysis>Wafer>Map Export>PNG"); });
            wafer.DropDownItems.Add(mapExp);
            wafer.DropDownItems.Add("Die Statistics", null, delegate { Evt("menu", "Analysis>Wafer>Die Statistics"); });
            ToolStripMenuItem trend = new ToolStripMenuItem("Trend");
            trend.DropDownItems.Add("Last 24h", null, delegate { Evt("menu", "Analysis>Trend>Last 24h"); });
            trend.DropDownItems.Add("Last 7 days", null, delegate { Evt("menu", "Analysis>Trend>Last 7 days"); });
            ana.DropDownItems.Add(wafer);
            ana.DropDownItems.Add(trend);
            ms.Items.AddRange(new ToolStripItem[] { file, rcp, run, tools, ana, help });

            ToolStrip ts = new ToolStrip();
            toolBar = ts;
            ts.ImageScalingSize = new Size(16, 16);
            ts.Items.Add("▶ Start", null, delegate { Delayed("start", StartRun); });
            ts.Items.Add("❚❚ Pause", null, delegate { Delayed("pause", TogglePause); });
            ts.Items.Add("■ Stop", null, delegate { StopRun(true); });
            ts.Items.Add(new ToolStripSeparator());
            ts.Items.Add("Alarm Reset", null, delegate { TruthLog.Write("alarm_reset", ""); lampWarn.On = false; warnBanner.Visible = false; Log("경고 표시 초기화"); });
            ts.Items.Add(new ToolStripSeparator());
            ts.Items.Add("Export", null, delegate { ExportResults(); });

            Controls.Add(ts);
            Controls.Add(ms);
            MainMenuStrip = ms;
        }

        void BuildStatus()
        {
            StatusStrip ss = new StatusStrip();
            stUser.Text = "User: " + user;
            stState.Text = "State: IDLE"; stState.Width = 160; stState.AutoSize = false;
            stRecipe.Text = "Recipe: -"; stRecipe.Spring = true; stRecipe.TextAlign = ContentAlignment.MiddleLeft;
            ss.Items.AddRange(new ToolStripItem[] { stUser, new ToolStripSeparator(), stState, new ToolStripSeparator(), stRecipe, stClock });
            Controls.Add(ss);
        }

        // ---------------------------------------------------------------- Recipe 탭
        TabPage BuildRecipeTab()
        {
            TabPage p = new TabPage("Recipe");
            recipeGrid.SetBounds(12, 12, 820, 700);
            recipeGrid.Anchor = AnchorStyles.Top | AnchorStyles.Bottom | AnchorStyles.Left;
            recipeGrid.ReadOnly = true; recipeGrid.AllowUserToAddRows = false; recipeGrid.AllowUserToDeleteRows = false;
            recipeGrid.SelectionMode = DataGridViewSelectionMode.FullRowSelect; recipeGrid.MultiSelect = false;
            recipeGrid.RowHeadersVisible = false; recipeGrid.AllowUserToResizeRows = false;
            recipeGrid.AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.Fill;
            recipeGrid.Columns.Add("id", "Recipe ID"); recipeGrid.Columns.Add("name", "Name (이름)");
            recipeGrid.Columns.Add("method", "Method"); recipeGrid.Columns.Add("dur", "Duration (s)");
            recipeGrid.Columns.Add("mod", "Modified");
            recipeGrid.Columns[1].FillWeight = 220;
            DateTime d0 = new DateTime(2026, 9, 1);
            foreach (Recipe r in recipes)
                recipeGrid.Rows.Add(r.Id, r.Name, r.Method, r.Duration, d0.AddDays(recipes.IndexOf(r) * 1.7).ToString("yyyy-MM-dd"));
            recipeGrid.SelectionChanged += delegate
            {
                if (recipeGrid.SelectedRows.Count > 0) TruthLog.Write("recipe_select", (string)recipeGrid.SelectedRows[0].Cells[0].Value);
            };
            recipeGrid.CellDoubleClick += delegate(object s, DataGridViewCellEventArgs e) { if (e.RowIndex >= 0) LoadSelected(); };

            GroupBox g = new GroupBox(); g.Text = "Recipe Parameters (레시피 파라미터)"; g.SetBounds(850, 12, 500, 470);
            int y = 36;
            AddRow(g, "LOT ID", lotBox, ref y);
            sampleBox.DropDownStyle = ComboBoxStyle.DropDownList;
            sampleBox.Items.AddRange(new object[] { "Wafer 300mm", "Wafer 200mm", "Coupon", "Powder" });
            sampleBox.SelectedIndex = 0;
            AddRow(g, "Sample Type", sampleBox, ref y);
            tempBox.Minimum = 20; tempBox.Maximum = 400; tempBox.Value = 25;
            AddRow(g, "Temperature (°C)", tempBox, ref y);
            repeatBox.Minimum = 1; repeatBox.Maximum = 10; repeatBox.Value = 1;
            AddRow(g, "Repeat (반복)", repeatBox, ref y);
            autoCal.Text = "Auto Calibration (자동 보정)"; autoCal.SetBounds(160, y, 300, 26); g.Controls.Add(autoCal); y += 34;
            saveRaw.Text = "Save Raw Data"; saveRaw.SetBounds(160, y, 300, 26); g.Controls.Add(saveRaw); y += 46;
            loadBtn.Text = "Load Recipe (불러오기)"; loadBtn.SetBounds(30, y, 200, 40);
            applyBtn.Text = "Apply Parameters"; applyBtn.SetBounds(250, y, 200, 40); applyBtn.Enabled = false;
            loadBtn.Click += delegate { LoadSelected(); };
            applyBtn.Click += delegate { Delayed("apply", ApplyParams); };
            g.Controls.Add(loadBtn); g.Controls.Add(applyBtn); y += 56;
            loadedLabel.Text = "Loaded: (없음)"; loadedLabel.SetBounds(30, y, 440, 50);
            loadedLabel.ForeColor = Color.FromArgb(30, 60, 120);
            g.Controls.Add(loadedLabel);
            EventHandler dirty = delegate { if (loaded != null) { paramsDirty = true; applyBtn.Enabled = true; } };
            lotBox.TextChanged += dirty; sampleBox.SelectedIndexChanged += dirty; tempBox.ValueChanged += dirty;
            repeatBox.ValueChanged += dirty; autoCal.CheckedChanged += dirty; saveRaw.CheckedChanged += dirty;

            p.Controls.Add(recipeGrid); p.Controls.Add(g);
            return p;
        }

        static void AddRow(Control parent, string label, Control c, ref int y)
        {
            Label l = new Label(); l.Text = label; l.SetBounds(20, y + 3, 135, 24);
            c.SetBounds(160, y, 300, 26);
            parent.Controls.Add(l); parent.Controls.Add(c);
            y += 40;
        }

        void LoadSelected()
        {
            if (state != "IDLE") { MessageBox.Show(this, "측정 중에는 레시피를 바꿀 수 없습니다.", "알림", MessageBoxButtons.OK, MessageBoxIcon.Information); return; }
            if (recipeGrid.SelectedRows.Count == 0) { MessageBox.Show(this, "레시피를 선택하세요.", "알림"); return; }
            Recipe r = recipes[recipeGrid.SelectedRows[0].Index];
            DialogResult a = MessageBox.Show(this, string.Format("레시피 {0} ({1}) 를 불러오시겠습니까?", r.Id, r.Name),
                "레시피 불러오기 (Load Recipe)", MessageBoxButtons.YesNo, MessageBoxIcon.Question);
            if (a != DialogResult.Yes) { TruthLog.Write("recipe_load_cancel", r.Id); return; }
            Delayed("load", delegate
            {
                loaded = r;
                loadedLabel.Text = string.Format("Loaded: {0}  {1}\nMethod {2} · {3} s · Spec {4:0.00}~{5:0.00} {6}", r.Id, r.Name, r.Method, r.Duration, r.SpecLo, r.SpecHi, r.Unit);
                stRecipe.Text = "Recipe: " + r.Id;
                paramsDirty = true; applyBtn.Enabled = true;
                TruthLog.Write("recipe_load", r.Id);
                Log("레시피 로드: " + r.Id);
                UpdateRunInfo();
            });
        }

        void ApplyParams()
        {
            if (loaded == null) return;
            paramsDirty = false; applyBtn.Enabled = false;
            string d = string.Format("lot={0};sample={1};temp={2};repeat={3};autocal={4};raw={5}",
                lotBox.Text.Trim(), sampleBox.Text, tempBox.Value, repeatBox.Value, autoCal.Checked, saveRaw.Checked);
            TruthLog.Write("params_apply", d);
            Log("파라미터 적용: " + d);
            UpdateRunInfo();
        }

        // ---------------------------------------------------------------- Run 탭
        TabPage BuildRunTab()
        {
            TabPage p = new TabPage("Run Monitor");
            GroupBox info = new GroupBox(); info.Text = "Run Info"; info.SetBounds(12, 12, 520, 170);
            runRecipe.SetBounds(16, 28, 490, 26); runLot.SetBounds(16, 58, 490, 26);
            runSample.SetBounds(16, 88, 490, 26); runCycle.SetBounds(16, 118, 490, 26);
            info.Controls.AddRange(new Control[] { runRecipe, runLot, runSample, runCycle });

            GroupBox lamps = new GroupBox(); lamps.Text = "Status (상태)"; lamps.SetBounds(550, 12, 500, 80);
            lampIdle = new Lamp("IDLE", Color.FromArgb(160, 160, 160));
            lampRun = new Lamp("RUN", Color.FromArgb(40, 200, 70));
            lampWarn = new Lamp("WARNING", Color.FromArgb(240, 190, 20));
            lampAlarm = new Lamp("ALARM", Color.FromArgb(230, 40, 40));
            Lamp[] all = { lampIdle, lampRun, lampWarn, lampAlarm };
            for (int i = 0; i < all.Length; i++) { all[i].Location = new Point(14 + i * 120, 26); lamps.Controls.Add(all[i]); }

            GroupBox meas = new GroupBox(); meas.Text = "Measurement (측정값)"; meas.SetBounds(550, 100, 640, 170);
            seg.Location = new Point(16, 30);
            unitLabel.Text = "nm"; unitLabel.Font = new Font("Malgun Gothic", 20f, FontStyle.Bold); unitLabel.SetBounds(490, 80, 120, 40);
            meas.Controls.Add(seg); meas.Controls.Add(unitLabel);

            progress.SetBounds(12, 290, 1178, 28);
            progressLabel.SetBounds(12, 322, 600, 26); progressLabel.Text = "Progress 0%   00:00 / 00:00";

            startBtn.Text = "▶ START"; startBtn.SetBounds(12, 200, 160, 70);
            startBtn.Font = new Font("Malgun Gothic", 13f, FontStyle.Bold); startBtn.BackColor = Color.FromArgb(200, 240, 200);
            pauseBtn.Text = "❚❚ PAUSE"; pauseBtn.SetBounds(186, 200, 160, 70); pauseBtn.Font = startBtn.Font;
            stopBtn.Text = "■ STOP"; stopBtn.SetBounds(360, 200, 160, 70); stopBtn.Font = startBtn.Font;
            stopBtn.BackColor = Color.FromArgb(250, 210, 210);
            startBtn.Click += delegate { Delayed("start", StartRun); };
            pauseBtn.Click += delegate { Delayed("pause", TogglePause); };
            stopBtn.Click += delegate { StopRun(true); };

            warnBanner.SetBounds(12, 356, 1178, 34); warnBanner.Visible = false;
            warnBanner.BackColor = Color.FromArgb(255, 230, 140); warnBanner.ForeColor = Color.FromArgb(120, 70, 0);
            warnBanner.Font = new Font("Malgun Gothic", 11f, FontStyle.Bold); warnBanner.TextAlign = ContentAlignment.MiddleLeft;

            busyLabel.Text = "  처리 중... (Processing)"; busyLabel.SetBounds(1000, 200, 190, 30); busyLabel.Visible = false;
            busyLabel.BackColor = Color.FromArgb(40, 40, 40); busyLabel.ForeColor = Color.White;

            Label ml = new Label(); ml.Text = "Messages"; ml.SetBounds(12, 398, 200, 22);
            msgList.SetBounds(12, 422, 1178, 300); msgList.Anchor = AnchorStyles.Top | AnchorStyles.Bottom | AnchorStyles.Left;
            p.Controls.AddRange(new Control[] { info, lamps, meas, startBtn, pauseBtn, stopBtn, progress, progressLabel, warnBanner, busyLabel, ml, msgList });
            return p;
        }

        void UpdateRunInfo()
        {
            runRecipe.Text = "Recipe : " + (loaded == null ? "-" : loaded.Id + "  " + loaded.Name);
            runLot.Text = "LOT ID : " + (lotBox.Text.Trim().Length == 0 ? "-" : lotBox.Text.Trim());
            runSample.Text = string.Format("Sample : {0}   Temp {1}°C   AutoCal {2}", sampleBox.Text, tempBox.Value, autoCal.Checked ? "ON" : "OFF");
            runCycle.Text = string.Format("Cycle  : {0} / {1}", state == "IDLE" ? 0 : cycle, repeatBox.Value);
            if (loaded != null) unitLabel.Text = loaded.Unit;
        }

        void SetState(string s)
        {
            state = s;
            stState.Text = "State: " + s;
            lampIdle.On = s == "IDLE";
            lampRun.On = s == "RUN";
            lampAlarm.On = s == "ALARM";
            startBtn.Enabled = s == "IDLE";
            pauseBtn.Enabled = s == "RUN" || s == "PAUSE";
            pauseBtn.Text = s == "PAUSE" ? "▶ RESUME" : "❚❚ PAUSE";
            stopBtn.Enabled = s != "IDLE";
            recipeGrid.Enabled = s == "IDLE";
            loadBtn.Enabled = s == "IDLE";
            UpdateRunInfo();
        }

        void StartRun()
        {
            if (state != "IDLE") return;
            if (loaded == null) { TruthLog.Write("start_rejected", "no_recipe"); MessageBox.Show(this, "레시피가 로드되지 않았습니다.\n(No recipe loaded)", "시작 불가", MessageBoxButtons.OK, MessageBoxIcon.Warning); return; }
            if (lotBox.Text.Trim().Length == 0) { TruthLog.Write("start_rejected", "no_lot"); MessageBox.Show(this, "LOT ID 를 입력하세요.\n(LOT ID required)", "시작 불가", MessageBoxButtons.OK, MessageBoxIcon.Warning); return; }
            if (paramsDirty) { TruthLog.Write("start_rejected", "params_not_applied"); MessageBox.Show(this, "변경된 파라미터를 먼저 적용(Apply)하세요.", "시작 불가", MessageBoxButtons.OK, MessageBoxIcon.Warning); return; }
            if (cfg.FreezePct > 0 && rnd.Next(100) < cfg.FreezePct)
            {
                TruthLog.Write("freeze", cfg.FreezeSec + "s");
                Thread.Sleep(cfg.FreezeSec * 1000);           // UI 멈춤 흉내 (화면 멈춤 감시 테스트)
            }
            cycles = (int)repeatBox.Value; cycle = 1;
            BeginCycle();
            tabs.SelectedIndex = 1;
            SetState("RUN");
            TruthLog.Write("run_start", string.Format("recipe={0};lot={1};cycles={2}", loaded.Id, lotBox.Text.Trim(), cycles));
            Log(string.Format("측정 시작 {0} LOT {1} ({2}회)", loaded.Id, lotBox.Text.Trim(), cycles));
        }

        void BeginCycle()
        {
            elapsed = 0; sum = 0; samples = 0;
            duration = Math.Max(3, loaded.Duration * cfg.TimeScale);
            progress.Value = 0;
        }

        void TogglePause()
        {
            if (state == "RUN") { SetState("PAUSE"); TruthLog.Write("run_pause", ""); Log("일시 정지"); }
            else if (state == "PAUSE") { SetState("RUN"); TruthLog.Write("run_resume", ""); Log("재개"); }
        }

        void StopRun(bool ask)
        {
            if (state == "IDLE") return;
            if (ask && MessageBox.Show(this, "측정을 중단하시겠습니까?\n(Abort measurement?)", "측정 중단", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes)
            {
                TruthLog.Write("stop_cancel", ""); return;
            }
            TruthLog.Write("run_stop", string.Format("cycle={0};elapsed={1:0.0}", cycle, elapsed));
            Log("측정 중단");
            SetState("IDLE");
            progress.Value = 0;
        }

        // 버튼 응답 지연 (느린 장비 SW): UI 는 살아 있고 '처리 중' 표시
        delegate void Action0();
        void Delayed(string what, Action0 act)
        {
            if (cfg.DelayMs <= 0) { act(); return; }
            busyLabel.Visible = true; busyLabel.BringToFront(); Cursor = Cursors.WaitCursor;
            System.Windows.Forms.Timer t = new System.Windows.Forms.Timer();
            t.Interval = cfg.DelayMs;
            t.Tick += delegate { t.Stop(); t.Dispose(); busyLabel.Visible = false; Cursor = Cursors.Default; act(); };
            t.Start();
        }

        void OnTick(object sender, EventArgs e)
        {
            DateTime now = DateTime.Now;
            double dt = (now - lastTick).TotalSeconds;
            lastTick = now;
            stClock.Text = now.ToString("yyyy-MM-dd HH:mm:ss");
            if (warnBanner.Visible && now > warnUntil) { warnBanner.Visible = false; lampWarn.On = false; }
            if (state != "RUN" || inAlarm) return;

            elapsed += dt;
            double v = loaded.Base * (1 + (rnd.NextDouble() - 0.5) * 0.04) + Math.Sin(elapsed) * loaded.Base * 0.005;
            sum += v; samples++;
            seg.Value = FormatValue(v);
            int pct = (int)Math.Min(100, elapsed / duration * 100);
            progress.Value = pct;
            progressLabel.Text = string.Format("Progress {0}%   {1:00}:{2:00} / {3:00}:{4:00}   Cycle {5}/{6}", pct,
                (int)elapsed / 60, (int)elapsed % 60, (int)duration / 60, (int)duration % 60, cycle, cycles);

            if (cfg.WarnPerMin > 0 && rnd.NextDouble() < cfg.WarnPerMin * dt / 60) RaiseWarning();
            if (cfg.AlarmPerMin > 0 && rnd.NextDouble() < cfg.AlarmPerMin * dt / 60) { RaiseAlarm(); return; }

            if (elapsed >= duration) FinishCycle();
        }

        static string FormatValue(double v)
        {
            string s = v.ToString("0.00", CultureInfo.InvariantCulture);
            return s.PadLeft(7, ' ');
        }

        void FinishCycle()
        {
            double avg = sum / Math.Max(1, samples);
            string judge = avg >= loaded.SpecLo && avg <= loaded.SpecHi ? "OK" : "NG";
            string val = avg.ToString("0.00", CultureInfo.InvariantCulture);
            seg.Value = FormatValue(avg);
            int row = resultGrid.Rows.Add(DateTime.Now.ToString("HH:mm:ss"), lotBox.Text.Trim(), loaded.Id, cycle + "/" + cycles, val, loaded.Unit, judge);
            resultGrid.Rows[row].Cells[6].Style.BackColor = judge == "OK" ? Color.FromArgb(200, 240, 200) : Color.FromArgb(250, 200, 200);
            TruthLog.Write("cycle_done", string.Format("recipe={0};lot={1};cycle={2};value={3};unit={4};judge={5}", loaded.Id, lotBox.Text.Trim(), cycle, val, loaded.Unit, judge));
            Log(string.Format("Cycle {0}/{1} 완료: {2} {3} ({4})", cycle, cycles, val, loaded.Unit, judge));
            if (cycle < cycles) { cycle++; BeginCycle(); UpdateRunInfo(); return; }
            SetState("IDLE");
            progress.Value = 100;
            TruthLog.Write("run_complete", string.Format("recipe={0};lot={1};last_value={2}", loaded.Id, lotBox.Text.Trim(), val));
            MessageBox.Show(this, string.Format("측정이 완료되었습니다.\n(Measurement completed)\n\n마지막 결과: {0} {1} ({2})", val, loaded.Unit, judge),
                "측정 완료", MessageBoxButtons.OK, MessageBoxIcon.Information);
            TruthLog.Write("complete_ack", "");
        }

        static readonly string[][] Alarms = {
            new string[] { "E-1032", "진공 압력이 설정값 이하입니다.\nVacuum pressure low (2.3e-3 Pa)" },
            new string[] { "E-2101", "스테이지 위치 오차가 허용 범위를 초과했습니다.\nStage position error" },
            new string[] { "E-3307", "검출기 온도 이상 (Detector over-temperature)" },
            new string[] { "E-4020", "샘플 로딩 실패 - 웨이퍼 감지 안 됨\nSample not detected" },
        };
        static readonly string[][] Warnings = {
            new string[] { "W-201", "온도 편차 경고 (Temperature deviation)" },
            new string[] { "W-305", "기준 시료 교정 주기 도래 (Calibration due)" },
        };

        void RaiseWarning()
        {
            string[] w = Warnings[rnd.Next(Warnings.Length)];
            warnBanner.Text = "  ⚠ " + w[0] + "  " + w[1];
            warnBanner.Visible = true; lampWarn.On = true;
            warnUntil = DateTime.Now.AddSeconds(6);
            AddAlarmLog(w[0], "WARN", w[1], "-");
            TruthLog.Write("warning", w[0]);
            Log("경고 " + w[0]);
        }

        void RaiseAlarm()
        {
            inAlarm = true;
            string[] a = Alarms[rnd.Next(Alarms.Length)];
            SetState("ALARM");
            TruthLog.Write("alarm_raised", a[0]);
            Log("알람 발생 " + a[0]);
            ListViewItem item = AddAlarmLog(a[0], "ALARM", a[1].Replace("\n", " "), "");
            using (AlarmForm f = new AlarmForm(a[0], a[1]))
            {
                f.ShowDialog(this);
                item.SubItems[4].Text = DateTime.Now.ToString("HH:mm:ss");
                inAlarm = false;
                lastTick = DateTime.Now;
                if (f.Abort)
                {
                    TruthLog.Write("alarm_abort", a[0]);
                    Log("알람으로 측정 중단 " + a[0]);
                    SetState("IDLE");
                    progress.Value = 0;
                }
                else
                {
                    TruthLog.Write("alarm_ack", a[0]);
                    Log("알람 확인 " + a[0]);
                    SetState("RUN");
                }
            }
        }

        // ---------------------------------------------------------------- Results / Alarm Log / Settings
        TabPage BuildResultTab()
        {
            TabPage p = new TabPage("Results");
            resultGrid.SetBounds(12, 12, 1340, 640);
            resultGrid.Anchor = AnchorStyles.Top | AnchorStyles.Bottom | AnchorStyles.Left | AnchorStyles.Right;
            resultGrid.ReadOnly = true; resultGrid.AllowUserToAddRows = false; resultGrid.RowHeadersVisible = false;
            resultGrid.AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.Fill;
            foreach (string c in new string[] { "Time", "LOT ID", "Recipe", "Cycle", "Value", "Unit", "Judge" }) resultGrid.Columns.Add(c, c);
            Button exp = new Button(); exp.Text = "Export CSV... (내보내기)"; exp.SetBounds(12, 664, 220, 38);
            exp.Anchor = AnchorStyles.Bottom | AnchorStyles.Left;
            exp.Click += delegate { ExportResults(); };
            Button clr = new Button(); clr.Text = "Clear (지우기)"; clr.SetBounds(246, 664, 160, 38);
            clr.Anchor = AnchorStyles.Bottom | AnchorStyles.Left;
            clr.Click += delegate
            {
                if (MessageBox.Show(this, "결과를 모두 지우시겠습니까?", "결과 지우기", MessageBoxButtons.YesNo, MessageBoxIcon.Question) == DialogResult.Yes)
                { resultGrid.Rows.Clear(); TruthLog.Write("results_clear", ""); }
            };
            p.Controls.AddRange(new Control[] { resultGrid, exp, clr });
            return p;
        }

        void ExportResults()
        {
            using (SaveFileDialog d = new SaveFileDialog())
            {
                d.Title = "결과 내보내기 (Export Results)";
                d.Filter = "CSV (*.csv)|*.csv";
                d.FileName = "GTB_results_" + DateTime.Now.ToString("yyyyMMdd_HHmm") + ".csv";
                if (d.ShowDialog(this) != DialogResult.OK) { TruthLog.Write("export_cancel", ""); return; }
                using (StreamWriter w = new StreamWriter(d.FileName, false, new UTF8Encoding(true)))
                {
                    w.WriteLine("Time,LOT ID,Recipe,Cycle,Value,Unit,Judge");
                    foreach (DataGridViewRow r in resultGrid.Rows)
                    {
                        string[] cells = new string[7];
                        for (int i = 0; i < 7; i++) cells[i] = Convert.ToString(r.Cells[i].Value);
                        w.WriteLine(string.Join(",", cells));
                    }
                }
                TruthLog.Write("export", d.FileName + ";rows=" + resultGrid.Rows.Count);
                Log("결과 저장: " + d.FileName);
            }
        }

        TabPage BuildAlarmTab()
        {
            TabPage p = new TabPage("Alarm Log");
            alarmList.SetBounds(12, 12, 1340, 690);
            alarmList.Anchor = AnchorStyles.Top | AnchorStyles.Bottom | AnchorStyles.Left | AnchorStyles.Right;
            alarmList.View = View.Details; alarmList.FullRowSelect = true; alarmList.GridLines = true;
            alarmList.Columns.Add("Time", 120); alarmList.Columns.Add("Code", 100); alarmList.Columns.Add("Level", 90);
            alarmList.Columns.Add("Message", 760); alarmList.Columns.Add("Ack Time", 120);
            p.Controls.Add(alarmList);
            return p;
        }

        ListViewItem AddAlarmLog(string code, string level, string msg, string ack)
        {
            ListViewItem it = new ListViewItem(new string[] { DateTime.Now.ToString("HH:mm:ss"), code, level, msg, ack });
            if (level == "ALARM") it.ForeColor = Color.FromArgb(190, 20, 20);
            alarmList.Items.Insert(0, it);
            return it;
        }

        // ---------------------------------------------------------------- Keyboard 탭 (조합키 시험)
        // ---------------------------------------------------------------- Complex UI 탭 (복잡한 UI 시험)
        // 조작 결과는 맨 위 LAST EVENT 와 정답 로그에 남는다 (GHOST 가 화면만 보고 채점할 수 있게)
        void Evt(string ev, string detail)
        {
            TruthLog.Write(ev, detail);
            cxLast.Text = "EVT " + ev + " " + detail;
        }

        TabPage BuildComplexTab()
        {
            TabPage p = new TabPage("Complex UI");
            cxTab = p;
            cxLast.SetBounds(12, 6, 1320, 40); cxLast.Font = new Font("Consolas", 18f, FontStyle.Bold); cxLast.Text = "EVT -";

            // 긴 드롭다운 (40개, 펼치면 스크롤 필요)
            Caption(p, "CHAMBER", 62);
            chamberBox.DropDownStyle = ComboBoxStyle.DropDownList; chamberBox.MaxDropDownItems = 8;
            for (int i = 1; i <= 40; i++) chamberBox.Items.Add(string.Format("Chamber-{0:00}", i));
            chamberBox.SetBounds(150, 58, 200, 28);
            chamberBox.SelectedIndexChanged += delegate { Evt("combo", (string)chamberBox.SelectedItem); };

            // 접힌 트리
            Caption(p, "RECIPE TREE", 100);
            recipeTree.SetBounds(12, 130, 338, 290); recipeTree.HideSelection = false;
            string[] bays = { "Bay-A", "Bay-B" };
            TreeNode fab = new TreeNode("Fab-1");
            foreach (string b in bays)
            {
                TreeNode bn = new TreeNode(b);
                for (int t = 1; t <= 2; t++)
                {
                    TreeNode tn = new TreeNode(string.Format("Tool-{0}{1}", b.Substring(4), t));
                    for (int c = 1; c <= 3; c++) tn.Nodes.Add(new TreeNode(string.Format("CH-{0}{1}-{2}", b.Substring(4), t, c)));
                    bn.Nodes.Add(tn);
                }
                fab.Nodes.Add(bn);
            }
            recipeTree.Nodes.Add(fab);
            recipeTree.AfterSelect += delegate(object s, TreeViewEventArgs e) { Evt("tree", e.Node.FullPath.Replace("\\", ">")); };

            // 우클릭 메뉴가 있는 목록
            Caption(p, "SLOT LIST", 432);
            slotList.SetBounds(12, 460, 338, 210);
            for (int i = 1; i <= 25; i++) slotList.Items.Add(string.Format("Slot {0:00}", i));
            ContextMenuStrip cm = new ContextMenuStrip();
            cm.Items.Add("Inspect", null, delegate { Evt("context", "Inspect " + slotList.SelectedItem); });
            cm.Items.Add("Exclude", null, delegate { Evt("context", "Exclude " + slotList.SelectedItem); });
            cm.Items.Add("Properties...", null, delegate { Evt("context", "Properties " + slotList.SelectedItem); });
            slotList.ContextMenuStrip = cm;
            slotList.MouseDown += delegate(object s, MouseEventArgs e)
            {
                int i = slotList.IndexFromPoint(e.Location);
                if (i >= 0) slotList.SelectedIndex = i;           // 우클릭한 줄을 선택
            };

            // 슬라이더
            Label gc = new Label(); gc.Text = "GAIN"; gc.SetBounds(372, 62, 60, 28); p.Controls.Add(gc);
            gainBar.SetBounds(430, 52, 360, 45); gainBar.Minimum = 0; gainBar.Maximum = 100; gainBar.Value = 50;
            gainBar.TickFrequency = 10; gainBar.SmallChange = 1; gainBar.LargeChange = 10;
            gainLabel.SetBounds(800, 58, 160, 30); gainLabel.Font = new Font("Consolas", 14f, FontStyle.Bold); gainLabel.Text = "GAIN = 50";
            gainBar.ValueChanged += delegate { gainLabel.Text = "GAIN = " + gainBar.Value; Evt("slider", gainBar.Value.ToString()); };

            // 표 (셀 클릭)
            waferGrid.SetBounds(372, 110, 560, 230);
            waferGrid.ReadOnly = true; waferGrid.AllowUserToAddRows = false; waferGrid.RowHeadersVisible = false;
            waferGrid.SelectionMode = DataGridViewSelectionMode.CellSelect; waferGrid.MultiSelect = false;
            waferGrid.AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.Fill;
            foreach (string h in new string[] { "Wafer", "Slot", "Site", "Thickness", "Judge" }) waferGrid.Columns.Add(h, h);
            Random r = new Random(11);
            for (int i = 1; i <= 8; i++)
                waferGrid.Rows.Add(string.Format("W{0:00}", i), (i * 3).ToString(), "S" + (1 + r.Next(9)),
                    (118 + r.NextDouble() * 6).ToString("0.00"), r.Next(6) == 0 ? "NG" : "OK");
            waferGrid.CellClick += delegate(object s, DataGridViewCellEventArgs e)
            {
                if (e.RowIndex >= 0 && e.ColumnIndex >= 0)
                    Evt("cell", string.Format("{0}/{1}={2}", waferGrid.Rows[e.RowIndex].Cells[0].Value,
                        waferGrid.Columns[e.ColumnIndex].HeaderText, waferGrid.Rows[e.RowIndex].Cells[e.ColumnIndex].Value));
            };

            // 탭 안의 탭
            TabControl sub = new TabControl(); sub.SetBounds(372, 360, 560, 230);
            TabPage sa = new TabPage("Sub A"), sb = new TabPage("Sub B"), sc = new TabPage("Sub C");
            Button runA = new Button(); runA.Text = "Run Sub A"; runA.SetBounds(20, 20, 160, 36);
            runA.Click += delegate { Evt("button", "Run Sub A"); };
            sa.Controls.Add(runA);
            CheckBox auto = new CheckBox(); auto.Text = "Enable Auto Recovery"; auto.SetBounds(20, 20, 300, 30);
            auto.CheckedChanged += delegate { Evt("check", "Enable Auto Recovery=" + (auto.Checked ? 1 : 0)); };
            sb.Controls.Add(auto);
            Label scl = new Label(); scl.Text = "Sub C: nothing here"; scl.SetBounds(20, 20, 300, 30); sc.Controls.Add(scl);
            sub.TabPages.AddRange(new TabPage[] { sa, sb, sc });
            sub.SelectedIndexChanged += delegate { Evt("subtab", sub.SelectedTab.Text); };

            // 글자 없는 웨이퍼 맵 (가장자리 좌표 글자만 있음)
            waferMap.SetBounds(950, 52, 390, 420);
            waferMap.DieClicked += delegate(string die) { Evt("die", die); };

            // 마우스를 올려야 나타나는 버튼
            Label hz = new Label(); hz.Text = "HOVER ZONE (마우스를 올리면 버튼이 나타남)"; hz.SetBounds(950, 490, 390, 24); p.Controls.Add(hz);
            Panel hover = new Panel(); hover.SetBounds(950, 516, 390, 74); hover.BorderStyle = BorderStyle.FixedSingle;
            hiddenBtn.Text = "Hidden Action"; hiddenBtn.SetBounds(110, 18, 170, 36); hiddenBtn.Visible = false;
            hiddenBtn.Click += delegate { Evt("button", "Hidden Action"); };
            hover.Controls.Add(hiddenBtn);
            hover.MouseEnter += delegate { hiddenBtn.Visible = true; hoverUntil = DateTime.Now.AddSeconds(3); };
            hiddenBtn.MouseEnter += delegate { hoverUntil = DateTime.Now.AddSeconds(3); };

            p.Controls.AddRange(new Control[] { cxLast, chamberBox, recipeTree, slotList, gainBar, gainLabel, waferGrid, sub, waferMap, hover });
            return p;
        }

        TabPage BuildKeyboardTab()
        {
            TabPage p = new TabPage("Keyboard");
            keyTab = p;
            Font big = new Font("Consolas", 24f, FontStyle.Bold), mid = new Font("Consolas", 16f, FontStyle.Bold);
            Caption(p, "LAST KEY", 16);
            keyLast.SetBounds(150, 8, 700, 50); keyLast.Font = big; keyLast.Text = "KEY -- SC -- E0 M -";
            Caption(p, "HELD", 76);
            keyHeld.SetBounds(150, 70, 280, 40); keyHeld.Font = mid; keyHeld.Text = "-";
            Label cc = new Label(); cc.Text = "COUNT"; cc.SetBounds(450, 76, 90, 30); p.Controls.Add(cc);
            keyCount.SetBounds(540, 70, 200, 40); keyCount.Font = mid; keyCount.Text = "0";
            Caption(p, "INPUT", 130);
            keyBox.Multiline = true; keyBox.AcceptsTab = true; keyBox.AcceptsReturn = true;
            keyBox.ScrollBars = ScrollBars.Vertical; keyBox.SetBounds(150, 126, 700, 120);
            Caption(p, "COPY FROM", 270);
            copySrc.ReadOnly = true; copySrc.Text = "GHOST-COPY-7319"; copySrc.SetBounds(150, 266, 300, 28);
            Caption(p, "PASTE TO", 310);
            pasteDst.SetBounds(150, 306, 300, 28);
            pasteDst.TextChanged += delegate { TruthLog.Write("paste_box", pasteDst.Text); };
            Caption(p, "CLIPBOARD", 350);
            clipLabel.SetBounds(150, 346, 700, 34); clipLabel.Font = new Font("Consolas", 14f); clipLabel.Text = "-";
            keyHist.SetBounds(880, 8, 460, 640); keyHist.Font = new Font("Consolas", 10f);
            p.Controls.AddRange(new Control[] { keyLast, keyHeld, keyCount, keyBox, copySrc, pasteDst, clipLabel, keyHist });
            Label note = new Label();
            note.Text = "이 탭에서 누른 키는 정답 로그(key)와 오른쪽 목록에 기록됩니다.\nKEY=가상키 SC=스캔코드 E=확장키 M=함께 눌린 수식키(C Ctrl, S Shift, A Alt, W Win)";
            note.SetBounds(150, 400, 700, 50); p.Controls.Add(note);
            tabs.SelectedIndexChanged += delegate { if (tabs.SelectedTab == keyTab) keyBox.Focus(); };
            return p;
        }

        static void Caption(Control p, string text, int y)
        {
            Label l = new Label(); l.Text = text; l.SetBounds(12, y, 130, 30); p.Controls.Add(l);
        }

        static bool Down(int vk) { return (GetKeyState(vk) & 0x8000) != 0; }

        static string Mods()
        {
            string m = (Down(0x11) ? "C" : "") + (Down(0x10) ? "S" : "") + (Down(0x12) ? "A" : "") + (Down(0x5B) || Down(0x5C) ? "W" : "");
            return m.Length > 0 ? m : "-";
        }

        public void OnRawKey(int vk, int sc, int ext, bool sys)
        {
            if (keyTab == null || tabs.SelectedTab != keyTab) return;
            string mods = Mods();
            string line = string.Format("KEY {0:X2} SC {1:X2} E{2} M {3}", vk, sc, ext, mods);
            TruthLog.Write("key", string.Format("vk=0x{0:X2};sc=0x{1:X2};ext={2};mods={3};sys={4}", vk, sc, ext, mods, sys ? 1 : 0));
            keyHist.Items.Insert(0, string.Format("{0,4} {1}", ++keyN, line));
            if (keyHist.Items.Count > 200) keyHist.Items.RemoveAt(keyHist.Items.Count - 1);
            bool modOnly = vk == 0x10 || vk == 0x11 || vk == 0x12 || (vk >= 0xA0 && vk <= 0xA5) || vk == 0x5B || vk == 0x5C;
            if (!modOnly) { keyLast.Text = line; keyCount.Text = (++keyK).ToString(); }   // COUNT: 수식키를 뺀 키 수
        }

        void KeyTabTick()
        {
            if (keyTab == null || tabs.SelectedTab != keyTab) return;
            keyHeld.Text = Mods();
            try
            {
                string c = Clipboard.ContainsText() ? Clipboard.GetText() : "(empty)";
                if (c.Length > 40) c = c.Substring(0, 40) + "...";
                if (clipLabel.Text != c) { clipLabel.Text = c; TruthLog.Write("clipboard", c); }
            }
            catch (Exception) { }
        }

        TabPage BuildSettingsTab()
        {
            TabPage p = new TabPage("Settings");
            GroupBox g = new GroupBox(); g.Text = "Test Difficulty (테스트 난이도)"; g.SetBounds(12, 12, 560, 380);
            int y = 34;
            setAlarm.DecimalPlaces = 1; setAlarm.Increment = 0.5m; setAlarm.Maximum = 20; setAlarm.Value = (decimal)cfg.AlarmPerMin;
            AddRow(g, "알람/분 (Alarm)", setAlarm, ref y);
            setWarn.DecimalPlaces = 1; setWarn.Increment = 0.5m; setWarn.Maximum = 20; setWarn.Value = (decimal)cfg.WarnPerMin;
            AddRow(g, "경고/분 (Warning)", setWarn, ref y);
            setDelay.Maximum = 5000; setDelay.Increment = 100; setDelay.Value = cfg.DelayMs;
            AddRow(g, "응답 지연 ms", setDelay, ref y);
            setFreeze.Maximum = 100; setFreeze.Value = cfg.FreezePct;
            AddRow(g, "멈춤 확률 %", setFreeze, ref y);
            setScale.DecimalPlaces = 1; setScale.Increment = 0.1m; setScale.Minimum = 0.1m; setScale.Maximum = 5; setScale.Value = (decimal)cfg.TimeScale;
            AddRow(g, "측정 시간 배율", setScale, ref y);
            setSmall.Text = "작은 글꼴 (Small font)"; setSmall.Checked = cfg.SmallFont; setSmall.SetBounds(160, y, 300, 26); g.Controls.Add(setSmall); y += 44;
            Button save = new Button(); save.Text = "Apply Settings"; save.SetBounds(160, y, 180, 38);
            save.Click += delegate
            {
                cfg.AlarmPerMin = (double)setAlarm.Value; cfg.WarnPerMin = (double)setWarn.Value; cfg.DelayMs = (int)setDelay.Value;
                cfg.FreezePct = (int)setFreeze.Value; cfg.TimeScale = (double)setScale.Value;
                if (cfg.SmallFont != setSmall.Checked) { cfg.SmallFont = setSmall.Checked; Font = Program.UiFont(cfg.SmallFont); }
                TruthLog.Write("settings", cfg.ToString());
                Log("설정 적용: " + cfg.ToString());
            };
            g.Controls.Add(save);
            Label note = new Label();
            note.Text = "정답 로그 (Truth log):\n" + TruthLog.PathName + "\n\n명령줄 예) GTB3000.exe /alarm=2 /warn=3 /delay=800 /freeze=20 /randompos /timescale=0.5 /style=flat\n스타일: native(OS 기본) · classic(고전) · flat(Win10/11 평면) · dark";
            note.SetBounds(600, 24, 740, 140);
            p.Controls.Add(g); p.Controls.Add(note);
            return p;
        }

        void Log(string m)
        {
            msgList.Items.Insert(0, DateTime.Now.ToString("HH:mm:ss") + "  " + m);
            if (msgList.Items.Count > 500) msgList.Items.RemoveAt(msgList.Items.Count - 1);
        }

        void OnClosing(object sender, FormClosingEventArgs e)
        {
            if (state != "IDLE")
            {
                if (MessageBox.Show(this, "측정 중입니다. 종료하시겠습니까?", "종료 확인", MessageBoxButtons.YesNo, MessageBoxIcon.Warning) != DialogResult.Yes)
                { e.Cancel = true; TruthLog.Write("exit_cancel", ""); return; }
            }
            else if (MessageBox.Show(this, "프로그램을 종료하시겠습니까?", "종료 (Exit)", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes)
            { e.Cancel = true; TruthLog.Write("exit_cancel", ""); return; }
            TruthLog.Write("exit", "");
        }
    }
}
