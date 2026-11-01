# -*- coding: utf-8 -*-
"""
Mobile Viewer Generator (scripts/generate_mobile_viewer.py).
Generates a zero-dependency, standalone mobile HTML web app and Markdown summary
for exploring 2026 J1 match tactical data, designed with progressive enhancement
so it works both with and without JavaScript (Google Drive preview friendly).
"""

from __future__ import annotations

import json
import logging
import socket
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agent.objective_profiler import resolve_team_name
from pipeline.db import DEFAULT_DB_PATH, get_db_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("generate_mobile_viewer")
DEFAULT_DB_PATH = ROOT_DIR / "data" / "football.db"
DEFAULT_STRUCTURED_DIR = ROOT_DIR / "data" / "structured"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "exports" / "mobile_viewer"


class MobileViewerGenerator:
    """Generates a progressive mobile HTML viewer and Markdown tactical summary."""

    def __init__(
        self,
        db_path: Path | str = DEFAULT_DB_PATH,
        structured_dir: Path | str = DEFAULT_STRUCTURED_DIR,
        output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    ) -> None:
        self.db_path = Path(db_path)
        self.structured_dir = Path(structured_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(self) -> Path:
        """Compile match records and structured json into a self-contained mobile HTML app."""
        matches = self._fetch_all_matches()
        items: List[Dict[str, Any]] = []

        for m in matches:
            m_id = m["match_id"]
            st_data = self._load_structured_json(m_id)
            item = {
                "match_id": m_id,
                "matchweek": m.get("matchweek") or 0,
                "date": m.get("date", ""),
                "home_id": m.get("home_team_id", ""),
                "away_id": m.get("away_team_id", ""),
                "home_name": resolve_team_name(m.get("home_team_id")),
                "away_name": resolve_team_name(m.get("away_team_id")),
                "home_score": m.get("home_score", 0),
                "away_score": m.get("away_score", 0),
                "stadium": m.get("stadium", ""),
                "structured": st_data if st_data else {},
            }
            items.append(item)

        # 1. Generate HTML (with server-side static rendering fallback)
        html_content = self._render_html(items)
        out_html = self.output_dir / "index.html"
        out_html.write_text(html_content, encoding="utf-8")
        logger.info(
            "Mobile Viewer HTML successfully generated -> %s (%d matches)",
            out_html,
            len(items),
        )

        # 2. Generate comprehensive Markdown version for Google Drive direct view
        md_content = self._render_markdown_summary(items)
        out_md = ROOT_DIR / "exports" / "J1_2026_全節戦術カルテ.md"
        out_md.write_text(md_content, encoding="utf-8")
        logger.info("Markdown Tactical Card generated -> %s", out_md)

        return out_html

    def _fetch_all_matches(self) -> List[Dict[str, Any]]:
        """Fetch all matches for season 2026 ordered by matchweek and date."""
        conn = get_db_connection(str(self.db_path))
        conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT match_id, season, matchweek, date, home_team_id, away_team_id,
                   home_score, away_score, stadium, weather, attendance
            FROM matches
            WHERE season = 2026
            ORDER BY matchweek DESC, date DESC;
            """,
        )
        rows = cursor.fetchall()
        conn.close()
        return rows

    def _load_structured_json(self, match_id: str) -> Optional[Dict[str, Any]]:
        """Load tactical json for match_id."""
        candidate = self.structured_dir / f"{match_id}_tactical.json"
        if candidate.exists():
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except Exception:
                pass
        for p in self.structured_dir.glob(f"*{match_id}*_tactical.json"):
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
        return None

    def _render_markdown_summary(self, items: List[Dict[str, Any]]) -> str:
        """Render a readable Markdown document for all matchweeks."""
        lines: List[str] = [
            "# ⚽ 2026明治安田J1リーグ 全節戦術カルテ",
            "",
            "> スマホのGoogleドライブやOneDriveでそのまま読める全節確定スタッツ＆戦術総括です。",
            "",
        ]

        mws = sorted(list(set(m["matchweek"] for m in items)), reverse=True)
        for mw in mws:
            lines.append(f"## 🏆 第{mw}節")
            mw_matches = [m for m in items if m["matchweek"] == mw]
            for m in mw_matches:
                st = m.get("structured", {})
                ft = st.get("deep_metrics", {}).get("field_tilt", {})
                lines.append(f"### 【第{mw}節】{m['home_name']} {m['home_score']} - {m['away_score']} {m['away_name']}")
                lines.append(f"- **日程・会場**: {m['date']} @ {m['stadium']}")
                lines.append(f"- **布陣**: {m['home_name']} [{st.get('home_formation', '不明')}] vs {m['away_name']} [{st.get('away_formation', '不明')}]")
                if ft:
                    lines.append(f"- **敵陣支配率 (Field Tilt)**: {m['home_name']} {ft.get('home_field_tilt', 50)}% : {m['away_name']} {ft.get('away_field_tilt', 50)}%")
                
                hl = st.get("tactical_highlights", [])
                if hl:
                    lines.append("- **戦術ハイライト**:")
                    for h in hl:
                        lines.append(f"  - {h}")
                
                phases = st.get("phases", [])
                if phases:
                    lines.append("- **時間帯別ダイナミクス**:")
                    for p in phases:
                        dom = m["home_name"] if p.get("dominant_team") == "HOME" else (m["away_name"] if p.get("dominant_team") == "AWAY" else "互角")
                        lines.append(f"  - **{p.get('phase', '-')}分** (主導権: {dom}): {p.get('momentum_summary', '')}")
                lines.append("")

        return "\n".join(lines)

    def _render_html(self, items: List[Dict[str, Any]]) -> str:
        """Render complete HTML/CSS/JS single-page web app with SSR fallback."""
        json_data_str = json.dumps(items, ensure_ascii=False)
        mws = sorted(list(set(m["matchweek"] for m in items)), reverse=True)

        static_sections_html = self._build_static_cards_html(items, mws)
        mw_options_html = self._build_mw_options_html(mws)
        mw_pills_html = self._build_mw_pills_html(mws)

        return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>J1戦術カルテ | スマホ知見ビューア</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700&family=Noto+Sans+JP:wght@400;500;700&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg: #0b0f19;
      --card-bg: rgba(26, 32, 53, 0.9);
      --card-border: rgba(255, 255, 255, 0.1);
      --accent: #3b82f6;
      --accent-glow: rgba(59, 130, 246, 0.35);
      --text: #f3f4f6;
      --text-muted: #9ca3af;
      --success: #10b981;
      --danger: #ef4444;
      --warning: #f59e0b;
    }}
    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      -webkit-tap-highlight-color: transparent;
    }}
    body {{
      font-family: 'Noto Sans JP', 'Outfit', sans-serif;
      background-color: var(--bg);
      color: var(--text);
      line-height: 1.5;
      padding-bottom: 80px;
    }}
    header {{
      position: sticky;
      top: 0;
      z-index: 50;
      backdrop-filter: blur(16px);
      background: rgba(11, 15, 25, 0.92);
      border-bottom: 1px solid var(--card-border);
      padding: 10px 14px;
    }}
    .header-title {{
      font-size: 1.1rem;
      font-weight: 700;
      letter-spacing: -0.02em;
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .badge-fct {{
      background: linear-gradient(135deg, #1d4ed8, #dc2626);
      color: white;
      font-size: 0.65rem;
      padding: 2px 6px;
      border-radius: 4px;
      font-weight: 700;
    }}
    .search-bar {{
      margin-top: 8px;
      display: flex;
      gap: 8px;
    }}
    .search-input, .filter-select {{
      background: rgba(255, 255, 255, 0.08);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      color: white;
      padding: 8px 10px;
      font-size: 0.85rem;
      outline: none;
    }}
    .search-input {{ flex: 1; }}
    .filter-select {{ width: 120px; }}
    
    /* Horizontal Scrolling Matchweek Pills */
    .pills-container {{
      display: flex;
      overflow-x: auto;
      gap: 6px;
      margin-top: 8px;
      padding-bottom: 4px;
      scrollbar-width: none;
      -ms-overflow-style: none;
    }}
    .pills-container::-webkit-scrollbar {{ display: none; }}
    .pill-btn {{
      display: inline-block;
      white-space: nowrap;
      background: rgba(255, 255, 255, 0.08);
      color: var(--text-muted);
      border: 1px solid var(--card-border);
      padding: 5px 12px;
      border-radius: 20px;
      font-size: 0.75rem;
      font-weight: 600;
      text-decoration: none;
      cursor: pointer;
    }}
    .pill-btn.active, .pill-btn:hover {{
      background: var(--accent);
      color: white;
      border-color: var(--accent);
    }}

    .container {{
      max-width: 600px;
      margin: 0 auto;
      padding: 12px 14px;
    }}
    .mw-heading {{
      font-size: 1.05rem;
      font-weight: 700;
      color: #60a5fa;
      margin: 18px 0 10px 0;
      padding-bottom: 4px;
      border-bottom: 2px solid rgba(59, 130, 246, 0.3);
      display: flex;
      align-items: center;
      gap: 6px;
    }}
    .match-card {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      margin-bottom: 12px;
      padding: 12px 14px;
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.35);
    }}
    .match-meta {{
      font-size: 0.75rem;
      color: var(--text-muted);
      display: flex;
      justify-content: space-between;
      margin-bottom: 6px;
    }}
    .score-board {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 8px;
    }}
    .team-block {{
      flex: 1;
      text-align: center;
    }}
    .team-name {{
      font-weight: 700;
      font-size: 0.95rem;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .score-center {{
      font-size: 1.5rem;
      font-weight: 800;
      font-family: 'Outfit', sans-serif;
      padding: 0 10px;
      letter-spacing: 2px;
      color: #60a5fa;
    }}
    /* Native Accordion for Zero-JS fallback */
    details.match-details {{
      margin-top: 8px;
      background: rgba(0, 0, 0, 0.25);
      border-radius: 8px;
      overflow: hidden;
      border: 1px solid rgba(255, 255, 255, 0.05);
    }}
    details.match-details > summary {{
      list-style: none;
      padding: 8px 10px;
      font-size: 0.8rem;
      font-weight: 600;
      color: #93c5fd;
      cursor: pointer;
      display: flex;
      justify-content: space-between;
      align-items: center;
      user-select: none;
    }}
    details.match-details > summary::-webkit-details-marker {{ display: none; }}
    details.match-details > summary::after {{
      content: '▼ 展開';
      font-size: 0.7rem;
      color: var(--text-muted);
    }}
    details.match-details[open] > summary::after {{
      content: '▲ 閉じる';
    }}
    .detail-content {{
      padding: 10px 12px;
      border-top: 1px solid rgba(255, 255, 255, 0.05);
      font-size: 0.8rem;
    }}
    .metric-row {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px;
      margin-bottom: 10px;
    }}
    .metric-card {{
      background: rgba(255, 255, 255, 0.04);
      border-radius: 6px;
      padding: 8px;
      text-align: center;
    }}
    .metric-label {{ font-size: 0.65rem; color: var(--text-muted); }}
    .metric-val {{ font-size: 1rem; font-weight: 700; color: #38bdf8; font-family: 'Outfit'; }}
    .section-title {{
      font-size: 0.82rem;
      font-weight: 700;
      color: #93c5fd;
      border-left: 3px solid var(--accent);
      padding-left: 6px;
      margin: 12px 0 6px 0;
    }}
    .phase-card {{
      background: rgba(255, 255, 255, 0.03);
      border-radius: 6px;
      padding: 8px;
      margin-bottom: 6px;
      font-size: 0.75rem;
    }}
    .phase-header {{
      font-weight: 700;
      color: #fde047;
      margin-bottom: 2px;
      display: flex;
      justify-content: space-between;
    }}
    .prompt-box {{
      background: #1e293b;
      border: 1px dashed var(--accent);
      border-radius: 6px;
      padding: 8px;
      font-size: 0.72rem;
      margin-top: 10px;
    }}
    .copy-btn {{
      background: var(--accent);
      color: white;
      border: none;
      padding: 5px 10px;
      border-radius: 4px;
      font-size: 0.72rem;
      font-weight: 600;
      margin-top: 4px;
      cursor: pointer;
    }}
  </style>
</head>
<body>

<header>
  <div class="header-title">
    ⚽ J1戦術カルテ <span class="badge-fct">2026 EDITION</span>
  </div>
  <div class="search-bar">
    <input type="text" id="searchInput" class="search-input" placeholder="チーム名や節で検索 (例: FC東京, 岡山)...">
    <select id="mwFilter" class="filter-select">
      {mw_options_html}
    </select>
  </div>
  <div class="pills-container" id="pillsBar">
    {mw_pills_html}
  </div>
</header>

<div class="container" id="matchList">
  {static_sections_html}
</div>

<script>
  const MATCHES = {json_data_str};

  function applyFilter() {{
    const query = document.getElementById('searchInput').value.trim().toLowerCase();
    const filter = document.getElementById('mwFilter').value;
    const cards = document.querySelectorAll('.match-card');
    const sections = document.querySelectorAll('.mw-section');

    // Update active pill button
    document.querySelectorAll('.pill-btn').forEach(btn => {{
      const bval = btn.getAttribute('data-val');
      if (bval === filter) {{
        btn.classList.add('active');
      }} else {{
        btn.classList.remove('active');
      }}
    }});

    let totalVisible = 0;

    sections.forEach(sec => {{
      const secMw = sec.getAttribute('data-mw');
      let secVisibleCount = 0;
      const secCards = sec.querySelectorAll('.match-card');

      secCards.forEach(card => {{
        const text = card.getAttribute('data-search') || '';
        const homeId = card.getAttribute('data-home-id') || '';
        const awayId = card.getAttribute('data-away-id') || '';

        const matchQuery = !query || text.includes(query);
        let matchFilter = true;
        if (filter === 'FCT') {{
          matchFilter = (homeId === 'FCT' || awayId === 'FCT');
        }} else if (filter !== 'ALL') {{
          matchFilter = (secMw === filter);
        }}

        if (matchQuery && matchFilter) {{
          card.style.display = 'block';
          secVisibleCount++;
          totalVisible++;
        }} else {{
          card.style.display = 'none';
        }}
      }});

      if (secVisibleCount > 0) {{
        sec.style.display = 'block';
      }} else {{
        sec.style.display = 'none';
      }}
    }});

    const noMatchesEl = document.getElementById('noMatchesMessage');
    if (noMatchesEl) {{
      noMatchesEl.style.display = (totalVisible === 0) ? 'block' : 'none';
    }}
  }}

  function selectPill(val) {{
    document.getElementById('mwFilter').value = val;
    applyFilter();
  }}

  function copyPrompt(btn) {{
    const box = btn.closest('.prompt-box');
    const p = box.querySelector('.prompt-text');
    if (p) {{
      navigator.clipboard.writeText(p.innerText).then(() => {{
        alert('プロンプトをクリップボードにコピーしました！NotebookLM等でご活用ください。');
      }}).catch(() => {{
        alert('コピーに失敗しました。手動でテキストを選択してください。');
      }});
    }}
  }}

  document.getElementById('searchInput').addEventListener('input', applyFilter);
  document.getElementById('mwFilter').addEventListener('change', applyFilter);
</script>
</body>
</html>
"""

    def _build_mw_options_html(self, mws: List[int]) -> str:
        """Build <option> tags for the select filter."""
        options = ['<option value="ALL">全節</option>', '<option value="FCT">FC東京のみ</option>']
        for mw in mws:
            options.append(f'<option value="{mw}">第{mw}節</option>')
        return "\n      ".join(options)

    def _build_mw_pills_html(self, mws: List[int]) -> str:
        """Build clickable horizontal pill buttons."""
        pills = [
            '<button type="button" class="pill-btn active" data-val="ALL" onclick="selectPill(\'ALL\')">全節</button>',
            '<button type="button" class="pill-btn" data-val="FCT" onclick="selectPill(\'FCT\')">FC東京のみ</button>',
        ]
        for mw in mws:
            pills.append(
                f'<button type="button" class="pill-btn" data-val="{mw}" onclick="selectPill(\'{mw}\')">第{mw}節</button>'
            )
        return "\n    ".join(pills)

    def _build_static_cards_html(self, items: List[Dict[str, Any]], mws: List[int]) -> str:
        """Generate static HTML cards grouped by matchweek with <details> for instant viewing."""
        sections: List[str] = []

        for mw in mws:
            mw_items = [m for m in items if m["matchweek"] == mw]
            cards_html: List[str] = []

            for m in mw_items:
                st = m.get("structured", {})
                deep = st.get("deep_metrics", {})
                conv = deep.get("conversion_rates", {})
                h_conv = conv.get("home", {})
                a_conv = conv.get("away", {})
                ft = deep.get("field_tilt", {})

                search_index = f"{m['home_name']} {m['away_name']} 第{mw}節 {m['stadium']} {m['date']}".lower()

                card_html = f"""
  <div class="match-card" data-mw="{mw}" data-home-id="{m['home_id']}" data-away-id="{m['away_id']}" data-search="{search_index}">
    <div class="match-meta">
      <span>第 {mw} 節 | {m['date']}</span>
      <span>{m['stadium']}</span>
    </div>
    <div class="score-board">
      <div class="team-block"><div class="team-name">{m['home_name']}</div></div>
      <div class="score-center">{m['home_score']} - {m['away_score']}</div>
      <div class="team-block"><div class="team-name">{m['away_name']}</div></div>
    </div>
    <details class="match-details">
      <summary>戦術カルテ・詳細スタッツ</summary>
      <div class="detail-content">
        <div class="section-title">布陣＆指標</div>
        <div style="font-size:0.75rem; margin-bottom:8px; color:#cbd5e1;">
          {m['home_name']} [{st.get('home_formation', '不明')}] vs {m['away_name']} [{st.get('away_formation', '不明')}]
        </div>
        <div class="metric-row">
          <div class="metric-card">
            <div class="metric-label">敵陣支配率 (Field Tilt)</div>
            <div class="metric-val">{ft.get('home_field_tilt', 50)}% : {ft.get('away_field_tilt', 50)}%</div>
          </div>
          <div class="metric-card">
            <div class="metric-label">進入変換率 (30m->PA)</div>
            <div class="metric-val">{h_conv.get('rate_30_to_pa', 0)}% : {a_conv.get('rate_30_to_pa', 0)}%</div>
          </div>
        </div>
        {self._render_details_body(m, st)}
      </div>
    </details>
  </div>"""
                cards_html.append(card_html)

            section_block = f"""
<section class="mw-section" id="mw-{mw}" data-mw="{mw}">
  <div class="mw-heading">🏆 第 {mw} 節 ({len(mw_items)}試合)</div>
  {"".join(cards_html)}
</section>"""
            sections.append(section_block)

        sections.append('<div id="noMatchesMessage" style="display:none; text-align:center; padding:40px; color:#9ca3af;">該当する試合が見つかりません</div>')
        return "\n".join(sections)

    def _render_details_body(self, m: Dict[str, Any], st: Dict[str, Any]) -> str:
        """Render inner tactical details body."""
        parts: List[str] = []

        # Context
        ctx = st.get("match_context", {})
        if ctx:
            fatigue = ctx.get("schedule_fatigue", {}).get("summary_text", "-")
            inj = ctx.get("injury_condition", {}).get("summary_text", "離脱者なし")
            disc = ctx.get("disciplinary", {}).get("summary_text", "停止なし")
            parts.append(f"""
        <div class="section-title">🛡️ 試合前提コンテキスト</div>
        <div style="background:rgba(15,23,42,0.6); border:1px solid #334155; border-radius:6px; padding:6px 8px; margin-bottom:8px; font-size:0.72rem; line-height:1.5;">
          <div><span style="color:#f97316;">🏥 怪我:</span> {inj}</div>
          <div><span style="color:#eab308;">🟨 規律:</span> {disc}</div>
          <div><span style="color:#60a5fa;">🗓️ 日程:</span> {fatigue}</div>
        </div>""")

        # Highlights
        hl = st.get("tactical_highlights", [])
        if hl:
            hl_items = "".join(f"<div style='margin-bottom:4px;'>• {h}</div>" for h in hl)
            parts.append(f"""
        <div class="section-title">戦術ハイライト</div>
        <div style="font-size:0.75rem; color:#e2e8f0; margin-bottom:8px;">{hl_items}</div>""")

        # Phases
        phases = st.get("phases", [])
        if phases:
            phase_cards = []
            for p in phases:
                dom = m['home_name'] if p.get('dominant_team') == 'HOME' else (m['away_name'] if p.get('dominant_team') == 'AWAY' else '互角')
                phase_cards.append(f"""
          <div class="phase-card">
            <div class="phase-header">
              <span>{p.get('phase', '-')}分</span>
              <span>主導権: {dom}</span>
            </div>
            <div>{p.get('momentum_summary', '')}</div>
          </div>""")
            parts.append(f"""
        <div class="section-title">時間帯別ダイナミクス</div>
        {"".join(phase_cards)}""")

        # Prompt box
        prompt_text = f"{m['date']}の{m['home_name']}対{m['away_name']}戦（{m['home_score']}-{m['away_score']}）において、両チームの勝敗を分けた構造的要因とプレッシングの攻防について詳しく分析してください。"
        parts.append(f"""
        <div class="prompt-box">
          <strong>💡 NotebookLMで仮説検証するプロンプト</strong>
          <p class="prompt-text" style="margin-top:3px;">{prompt_text}</p>
          <button type="button" class="copy-btn" onclick="copyPrompt(this)">プロンプトをコピー</button>
        </div>""")

        return "".join(parts)


def get_local_ip() -> str:
    """Detect local IP address of current machine."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


if __name__ == "__main__":
    generator = MobileViewerGenerator()
    out_file = generator.generate()
    ip = get_local_ip()
    print("\n" + "=" * 60)
    print(" [MOBILE VIEWER] HTML & Markdown generation completed!")
    print(f" File path: {out_file.resolve()}")
    print("=" * 60)
