"""일회성 패치: GTB-3000 Keyboard 탭 (키 입력 정답 기록·화면 표시, 복사·붙여넣기 시험 칸)."""
import sys

p = sys.argv[1]
s = open(p, encoding="utf-8").read()


def rep(a, b):
    global s
    assert a in s, a[:70]
    s = s.replace(a, b, 1)


rep("""using System.Windows.Forms;
""", """using System.Windows.Forms;
using System.Runtime.InteropServices;
""")

rep("""    // ------------------------------------------------------------------ 정답 로그""",
"""    // ------------------------------------------------------------------ 키 입력 기록 (Keyboard 탭)
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

    // ------------------------------------------------------------------ 정답 로그""")

rep("""        System.Windows.Forms.Timer uiTimer = new System.Windows.Forms.Timer();""",
"""        System.Windows.Forms.Timer uiTimer = new System.Windows.Forms.Timer();
        // Keyboard 탭
        [DllImport("user32.dll")] static extern short GetKeyState(int vk);
        TabPage keyTab;
        Label keyLast = new Label(), keyHeld = new Label(), keyCount = new Label(), clipLabel = new Label();
        TextBox keyBox = new TextBox(), copySrc = new TextBox(), pasteDst = new TextBox();
        ListBox keyHist = new ListBox();
        int keyN;""")

rep("""            tabs.TabPages.Add(BuildSettingsTab());""",
"""            tabs.TabPages.Add(BuildSettingsTab());
            tabs.TabPages.Add(BuildKeyboardTab());
            KeyRecorder kr = new KeyRecorder(); kr.Owner = this;
            Application.AddMessageFilter(kr);""")

rep("""        TabPage BuildSettingsTab()""",
"""        // ---------------------------------------------------------------- Keyboard 탭 (조합키 시험)
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
            note.Text = "이 탭에서 누른 키는 정답 로그(key)와 오른쪽 목록에 기록됩니다.\\nKEY=가상키 SC=스캔코드 E=확장키 M=함께 눌린 수식키(C Ctrl, S Shift, A Alt, W Win)";
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
            if (!modOnly) { keyLast.Text = line; keyCount.Text = keyN.ToString(); }
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

        TabPage BuildSettingsTab()""")

rep("""            tick.Tick += new EventHandler(OnTick);""",
"""            tick.Tick += new EventHandler(OnTick);
            tick.Tick += delegate { KeyTabTick(); };""")

open(p, "w", encoding="utf-8").write(s)
print("ok")
