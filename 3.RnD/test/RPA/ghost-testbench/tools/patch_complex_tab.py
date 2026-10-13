"""일회성 패치: GTB-3000 Complex UI 탭 (복잡한 UI 시험) + Analysis 다단계 메뉴."""
import sys

p = sys.argv[1]
s = open(p, encoding="utf-8").read()


def rep(a, b):
    global s
    assert a in s, a[:70]
    s = s.replace(a, b, 1)


# ---- 다단계 메뉴
rep("""            ms.Items.AddRange(new ToolStripItem[] { file, rcp, run, tools, help });""",
"""            ToolStripMenuItem ana = new ToolStripMenuItem("Analysis");
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
            ms.Items.AddRange(new ToolStripItem[] { file, rcp, run, tools, ana, help });""")

# ---- 필드
rep("""        int keyN, keyK;""",
"""        int keyN, keyK;
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
        DateTime hoverUntil;""")

rep("""            tabs.TabPages.Add(BuildKeyboardTab());""",
"""            tabs.TabPages.Add(BuildKeyboardTab());
            tabs.TabPages.Add(BuildComplexTab());""")

# ---- 탭 구성
rep("""        TabPage BuildKeyboardTab()""",
"""        // ---------------------------------------------------------------- Complex UI 탭 (복잡한 UI 시험)
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
            recipeTree.AfterSelect += delegate(object s, TreeViewEventArgs e) { Evt("tree", e.Node.FullPath.Replace("\\\\", ">")); };

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

        TabPage BuildKeyboardTab()""")

# 마우스가 떠나면 3초 뒤 숨김 (타이머)
rep("""            tick.Tick += delegate { KeyTabTick(); };""",
"""            tick.Tick += delegate { KeyTabTick(); };
            tick.Tick += delegate
            {
                if (hiddenBtn.Visible && DateTime.Now > hoverUntil && !hiddenBtn.Parent.ClientRectangle.Contains(hiddenBtn.Parent.PointToClient(Cursor.Position)))
                    hiddenBtn.Visible = false;
            };""")

# ---- 웨이퍼 맵 컨트롤
rep("""    // ------------------------------------------------------------------ 정답 로그""",
"""    // ------------------------------------------------------------------ 웨이퍼 맵 (글자 없는 그림 요소)
    // 13 x 13 격자, 원 밖 칸은 없음. 위에 열 글자 A~M, 왼쪽에 행 숫자 1~13. 칸을 누르면 선택 표시 + 이벤트
    class WaferMap : Control
    {
        public delegate void DieHandler(string die);
        public event DieHandler DieClicked;
        const int N = 13, Cell = 26, Left0 = 40, Top0 = 40;
        string selected = "";

        public WaferMap() { DoubleBuffered = true; BackColor = Color.White; }

        static string Name(int c, int r) { return ((char)('A' + c)).ToString() + (r + 1); }

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
                    bool sel = Name(c, r) == selected;
                    int k = (c * 7 + r * 13) % 10;                       // 측정값 색 (녹~황)
                    using (Brush b = new SolidBrush(sel ? Color.FromArgb(220, 40, 40) : Color.FromArgb(80 + k * 12, 170, 90)))
                        g.FillRectangle(b, rc);
                }
        }

        protected override void OnMouseClick(MouseEventArgs e)
        {
            int c = (e.X - Left0) / Cell, r = (e.Y - Top0) / Cell;
            if (e.X < Left0 || e.Y < Top0 || c >= N || r >= N || !OnWafer(c, r)) return;
            selected = Name(c, r);
            Invalidate();
            if (DieClicked != null) DieClicked(selected);
        }
    }

    // ------------------------------------------------------------------ 정답 로그""")

open(p, "w", encoding="utf-8").write(s)
print("ok")
