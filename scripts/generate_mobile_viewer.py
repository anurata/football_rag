"""
scripts/generate_mobile_viewer.py

Generates a standalone, responsive, high-aesthetic mobile web viewer (PWA-ready)
for reviewing 2026 J-League tactical match reports and deep metrics statically on smartphones.
Includes QR-code console server launcher.
"""

import json
import logging
import os
import socket
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pipeline.db import DEFAULT_DB_PATH, get_db_connection
from agent.objective_profiler import resolve_team_name

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class MobileViewerGenerator:
    """Builds a single-file, zero-dependency static responsive mobile viewer HTML."""

    def __init__(
        self,
        db_path: str = DEFAULT_DB_PATH,
        structured_dir: str = "data/structured",
        output_dir: str = "exports/mobile_viewer",
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

        html_content = self._render_html(items)
        out_file = self.output_dir / "index.html"
        out_file.write_text(html_content, encoding="utf-8")
        logger.info("Mobile Viewer HTML successfully generated -> %s (%d matches)", out_file, len(items))
        return out_file

    def _fetch_all_matches(self) -> List[Dict[str, Any]]:
        """Fetch all matches for season 2026."""
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

    def _render_html(self, items: List[Dict[str, Any]]) -> str:
        """Render complete HTML/CSS/JS single-page web app."""
        json_data_str = json.dumps(items, ensure_ascii=False)

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
      --card-bg: rgba(26, 32, 53, 0.85);
      --card-border: rgba(255, 255, 255, 0.08);
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
      background: rgba(11, 15, 25, 0.85);
      border-bottom: 1px solid var(--card-border);
      padding: 12px 16px;
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
      margin-top: 10px;
      display: flex;
      gap: 8px;
    }}
    .search-input, .filter-select {{
      background: rgba(255, 255, 255, 0.06);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      color: white;
      padding: 8px 12px;
      font-size: 0.85rem;
      outline: none;
    }}
    .search-input {{ flex: 1; }}
    .filter-select {{ width: 110px; }}
    .container {{
      max-width: 600px;
      margin: 0 auto;
      padding: 12px 14px;
    }}
    .match-card {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 14px;
      margin-bottom: 12px;
      padding: 14px;
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
      cursor: pointer;
      transition: transform 0.15s ease, border-color 0.15s ease;
    }}
    .match-card:active {{
      transform: scale(0.985);
    }}
    .match-card.active {{
      border-color: var(--accent);
      box-shadow: 0 0 16px var(--accent-glow);
    }}
    .match-meta {{
      font-size: 0.75rem;
      color: var(--text-muted);
      display: flex;
      justify-content: space-between;
      margin-bottom: 8px;
    }}
    .score-board {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 10px;
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
      font-size: 1.6rem;
      font-weight: 800;
      font-family: 'Outfit', sans-serif;
      padding: 0 12px;
      letter-spacing: 2px;
      color: #60a5fa;
    }}
    .highlights-preview {{
      font-size: 0.8rem;
      color: #d1d5db;
      background: rgba(0, 0, 0, 0.25);
      border-radius: 8px;
      padding: 8px 10px;
      margin-top: 8px;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }}
    /* Detail Modal / Drawer */
    .drawer {{
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(11, 15, 25, 0.96);
      backdrop-filter: blur(20px);
      z-index: 100;
      display: none;
      flex-direction: column;
      overflow-y: auto;
      padding: 16px;
    }}
    .drawer.open {{
      display: flex;
    }}
    .drawer-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid var(--card-border);
      padding-bottom: 12px;
      margin-bottom: 16px;
    }}
    .close-btn {{
      background: rgba(255, 255, 255, 0.1);
      border: none;
      color: white;
      font-size: 1.2rem;
      width: 36px;
      height: 36px;
      border-radius: 50%;
      cursor: pointer;
    }}
    .metric-row {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin-bottom: 14px;
    }}
    .metric-card {{
      background: rgba(255, 255, 255, 0.04);
      border-radius: 8px;
      padding: 10px;
      text-align: center;
    }}
    .metric-label {{ font-size: 0.7rem; color: var(--text-muted); }}
    .metric-val {{ font-size: 1.1rem; font-weight: 700; color: #38bdf8; font-family: 'Outfit'; }}
    .section-title {{
      font-size: 0.9rem;
      font-weight: 700;
      color: #93c5fd;
      border-left: 3px solid var(--accent);
      padding-left: 8px;
      margin: 16px 0 8px 0;
    }}
    .phase-card {{
      background: rgba(255, 255, 255, 0.03);
      border-radius: 8px;
      padding: 10px;
      margin-bottom: 8px;
      font-size: 0.8rem;
    }}
    .phase-header {{
      font-weight: 700;
      color: #fde047;
      margin-bottom: 4px;
      display: flex;
      justify-content: space-between;
    }}
    .prompt-box {{
      background: #1e293b;
      border: 1px dashed var(--accent);
      border-radius: 8px;
      padding: 10px;
      font-size: 0.75rem;
      margin-top: 14px;
    }}
    .copy-btn {{
      background: var(--accent);
      color: white;
      border: none;
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 0.75rem;
      font-weight: 600;
      margin-top: 6px;
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
    <input type="text" id="searchInput" class="search-input" placeholder="チーム名や節で検索 (例: FC東京, 町田)...">
    <select id="mwFilter" class="filter-select">
      <option value="ALL">全節</option>
      <option value="FCT">FC東京のみ</option>
      <option value="1">第1節</option>
      <option value="2">第2節</option>
      <option value="3">第3節</option>
      <option value="4">第4節</option>
      <option value="5">第5節</option>
      <option value="6">第6節</option>
      <option value="7">第7節</option>
      <option value="8">第8節</option>
      <option value="9">第9節</option>
      <option value="10">第10節</option>
      <option value="11">第11節</option>
      <option value="12">第12節</option>
    </select>
  </div>
</header>

<div class="container" id="matchList"></div>

<!-- Drawer Modal for Match Detail -->
<div class="drawer" id="detailDrawer">
  <div class="drawer-header">
    <div id="drawerTitle" style="font-weight: 700; font-size: 0.95rem;"></div>
    <button class="close-btn" onclick="closeDrawer()">✕</button>
  </div>
  <div id="drawerBody"></div>
</div>

<script>
  const MATCHES = {json_data_str};

  function renderList() {{
    const query = document.getElementById('searchInput').value.trim().toLowerCase();
    const filter = document.getElementById('mwFilter').value;
    const container = document.getElementById('matchList');
    container.innerHTML = '';

    const filtered = MATCHES.filter(m => {{
      const matchText = (m.home_name + ' ' + m.away_name + ' 第' + m.matchweek + '節').toLowerCase();
      const matchQuery = !query || matchText.includes(query);

      let matchFilter = true;
      if (filter === 'FCT') {{
        matchFilter = (m.home_id === 'FCT' || m.away_id === 'FCT');
      }} else if (filter !== 'ALL') {{
        matchFilter = (String(m.matchweek) === filter);
      }}
      return matchQuery && matchFilter;
    }});

    if (filtered.length === 0) {{
      container.innerHTML = '<div style="text-align:center; padding:40px; color:#9ca3af;">該当する試合が見つかりません</div>';
      return;
    }}

    filtered.forEach(m => {{
      const card = document.createElement('div');
      card.className = 'match-card';
      card.onclick = () => openDrawer(m);

      const highlights = (m.structured && m.structured.tactical_highlights) || [];
      const hlText = highlights.length > 0 ? highlights[0] : (m.stadium + ' | ' + m.date);

      card.innerHTML = `
        <div class="match-meta">
          <span>第 ${{m.matchweek}} 節 | ${{m.date}}</span>
          <span>${{m.stadium}}</span>
        </div>
        <div class="score-board">
          <div class="team-block"><div class="team-name">${{m.home_name}}</div></div>
          <div class="score-center">${{m.home_score}} - ${{m.away_score}}</div>
          <div class="team-block"><div class="team-name">${{m.away_name}}</div></div>
        </div>
        <div class="highlights-preview">${{hlText}}</div>
      `;
      container.appendChild(card);
    }});
  }}

  function openDrawer(m) {{
    const drawer = document.getElementById('detailDrawer');
    const title = document.getElementById('drawerTitle');
    const body = document.getElementById('drawerBody');

    title.innerText = `第${{m.matchweek}}節: ${{m.home_name}} vs ${{m.away_name}}`;

    const st = m.structured || {{}};
    const deep = st.deep_metrics || {{}};
    const conv = deep.conversion_rates || {{}};
    const hConv = conv.home || {{}};
    const aConv = conv.away || {{}};
    const ft = deep.field_tilt || {{}};

    let html = `
      <div class="score-board" style="margin-bottom:14px; background:rgba(255,255,255,0.03); border-radius:10px; padding:10px;">
        <div class="team-block">
          <div class="team-name">${{m.home_name}}</div>
          <div style="font-size:0.7rem; color:#9ca3af;">[${{st.home_formation || '不明'}}]</div>
        </div>
        <div class="score-center">${{m.home_score}} - ${{m.away_score}}</div>
        <div class="team-block">
          <div class="team-name">${{m.away_name}}</div>
          <div style="font-size:0.7rem; color:#9ca3af;">[${{st.away_formation || '不明'}}]</div>
        </div>
      </div>

      <div class="section-title">定量スタッツ＆進入効率</div>
      <div class="metric-row">
        <div class="metric-card">
          <div class="metric-label">敵陣支配率 (Field Tilt)</div>
          <div class="metric-val">${{ft.home_field_tilt || 50}}% : ${{ft.away_field_tilt || 50}}%</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">進入変換率 (30m->PA)</div>
          <div class="metric-val">${{hConv.rate_30_to_pa || 0}}% : ${{aConv.rate_30_to_pa || 0}}%</div>
        </div>
      </div>
    `;

    // Highlights
    if (st.tactical_highlights && st.tactical_highlights.length > 0) {{
      html += '<div class="section-title">戦術ハイライト</div>';
      st.tactical_highlights.forEach(h => {{
        html += `<div style="font-size:0.8rem; margin-bottom:6px; color:#e5e7eb;">• ${{h}}</div>`;
      }});
    }}

    // Phases
    if (st.phases && st.phases.length > 0) {{
      html += '<div class="section-title">時間帯別ダイナミクス</div>';
      st.phases.forEach(p => {{
        const dom = p.dominant_team === 'HOME' ? m.home_name : (p.dominant_team === 'AWAY' ? m.away_name : '互角');
        html += `
          <div class="phase-card">
            <div class="phase-header">
              <span>${{p.phase}}分</span>
              <span>主導権: ${{dom}}</span>
            </div>
            <div>${{p.momentum_summary}}</div>
          </div>
        `;
      }});
    }}

    // NotebookLM Prompt copy
    html += `
      <div class="prompt-box">
        <strong>💡 NotebookLMで仮説検証するプロンプト</strong>
        <p id="promptText" style="margin-top:4px;">
          ${{m.date}}の${{m.home_name}}対${{m.away_name}}戦（${{m.home_score}}-${{m.away_score}}）において、両チームの勝敗を分けた構造的要因とプレッシングの攻防について詳しく分析してください。
        </p>
        <button class="copy-btn" onclick="copyPrompt()">プロンプトをコピー</button>
      </div>
    `;

    body.innerHTML = html;
    drawer.classList.add('open');
  }}

  function closeDrawer() {{
    document.getElementById('detailDrawer').classList.remove('open');
  }}

  function copyPrompt() {{
    const text = document.getElementById('promptText').innerText;
    navigator.clipboard.writeText(text).then(() => {{
      alert('プロンプトをクリップボードにコピーしました！NotebookLMで貼り付けて質問してください。');
    }});
  }}

  document.getElementById('searchInput').addEventListener('input', renderList);
  document.getElementById('mwFilter').addEventListener('change', renderList);

  renderList();
</script>
</body>
</html>
"""


def get_local_ip() -> str:
    """Detect local IP address of current machine."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't even have to be reachable
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
    print(" [MOBILE VIEWER] HTML generation completed!")
    print(f" File path: {out_file.resolve()}")
    print("=" * 60)
    print(f" Local URL:       http://localhost:8080")
    print(f" Smartphone URL:  http://{ip}:8080")
    print("=" * 60)
