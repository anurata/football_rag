import os
import re
import urllib.request
from bs4 import BeautifulSoup


def fetch_html(url: str, timeout: int = 15) -> str:
    """指定されたURLからHTMLテキストを取得する。"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def extract_flab_report_text(soup: BeautifulSoup) -> str:
    """戦評テキストを抽出する。"""
    for h in soup.find_all(["h3", "h4"]):
        if "戦評" in h.get_text():
            cpt = h.find_next_sibling(class_=lambda c: c and "cpt" in c)
            if cpt:
                return cpt.get_text("\n", strip=True)
    return "戦評データなし"


def _parse_player_row(tr) -> dict:
    """選手行（tr）からポジション、背番号、選手名、出場時間、カード、交代を抽出する。"""
    tds = tr.find_all(["th", "td"])
    if len(tds) < 5:
        return {}

    pos = tds[0].get_text(strip=True)
    number = tds[1].get_text(strip=True)
    name = tds[4].get_text(strip=True) if len(tds) > 4 else ""
    minutes = tds[5].get_text(strip=True) if len(tds) > 5 else ""

    # カードや交代判定
    card = "-"
    change = "フル出場" if ("90分" in minutes or not minutes) else "交代"

    for img in tr.find_all("img"):
        src = img.get("src", "")
        if "R0lGODlhCQALAIAAAP/Y" in src:
            card = "警告(1)"
        elif "yellow2" in src:
            card = "警告(2)"
        elif "red" in src:
            card = "退場"
        if "out" in src or "AAAIVJREFUeNpiZGVlZUAGq1" in src:
            change = "途中交代OUT"
        elif "in" in src:
            change = "途中出場IN"

    return {
        "position": pos,
        "number": number,
        "name": name,
        "minutes": minutes,
        "change": change,
        "card": card,
    }


def extract_flab_players(soup: BeautifulSoup) -> dict:
    """HOME / AWAYのスターティングメンバーおよびベンチメンバーを抽出する。"""
    result = {
        "home": {
            "name": "HOME",
            "coach": "",
            "starting": [],
            "substitutes": [],
        },
        "away": {
            "name": "AWAY",
            "coach": "",
            "starting": [],
            "substitutes": [],
        },
    }

    # チーム名取得
    tbl_compare = soup.find(class_=lambda c: c and "tblCompare" in c)
    if tbl_compare:
        dsktp_spans = tbl_compare.find_all(class_="dsktp")
        if len(dsktp_spans) >= 2:
            result["home"]["name"] = dsktp_spans[0].get_text(strip=True)
            result["away"]["name"] = dsktp_spans[1].get_text(strip=True)

    tables = soup.find_all("table")
    # Table 2: Home Starting, Table 3: Home Subs, Table 4: Away Starting, Table 5: Away Subs
    if len(tables) >= 6:
        # Home Starting
        for tr in tables[2].find_all("tr"):
            row = _parse_player_row(tr)
            if row.get("name"):
                result["home"]["starting"].append(row)

        # Home Subs
        for tr in tables[3].find_all("tr"):
            txt = tr.get_text(strip=True)
            if "監督" in txt:
                result["home"]["coach"] = txt
                continue
            row = _parse_player_row(tr)
            if row.get("name"):
                result["home"]["substitutes"].append(row)

        # Away Starting
        for tr in tables[4].find_all("tr"):
            row = _parse_player_row(tr)
            if row.get("name"):
                result["away"]["starting"].append(row)

        # Away Subs
        for tr in tables[5].find_all("tr"):
            txt = tr.get_text(strip=True)
            if "監督" in txt:
                result["away"]["coach"] = txt
                continue
            row = _parse_player_row(tr)
            if row.get("name"):
                result["away"]["substitutes"].append(row)

    return result


def extract_flab_stats(soup: BeautifulSoup) -> list[dict]:
    """チーム全スタッツ（ゴール期待値、シュート、走行距離、スプリント等）を抽出する。"""
    stats_list = []
    # statsTbl6 でスタッツ項目を含むテーブルを探す
    for tbl in soup.find_all("table", class_=lambda c: c and "statsTbl6" in c):
        trs = tbl.find_all("tr")
        i = 0
        while i < len(trs):
            cells = [td.get_text(strip=True) for td in trs[i].find_all(["th", "td"])]
            # 指標名のみの行がある場合（例: 'ゴール期待値'）
            if len(cells) == 1 and cells[0]:
                stat_name = cells[0]
                if i + 1 < len(trs):
                    val_cells = [td.get_text(strip=True) for td in trs[i + 1].find_all(["th", "td"])]
                    # 行形式: 今季平均(H) | 成功率(H) | 総数(H) | 項目名 | 総数(A) | 成功率(A) | 今季平均(A)
                    if len(val_cells) >= 7:
                        stats_list.append(
                            {
                                "name": stat_name,
                                "home_val": val_cells[2],
                                "home_rate": val_cells[1],
                                "home_avg": val_cells[0],
                                "away_val": val_cells[4],
                                "away_rate": val_cells[5],
                                "away_avg": val_cells[6],
                            },
                        )
                    i += 2
                    continue
            i += 1

    return stats_list


def extract_flab_cbp(soup: BeautifulSoup) -> dict:
    """チャンスビルディングポイント（チーム比較および全8カテゴリの選手ランキング）を抽出する。"""
    cbp_data = {
        "team": [],
        "categories": {},
    }

    category_names = {
        "1": "攻撃",
        "2": "パス",
        "3": "クロス",
        "4": "ドリブル",
        "5": "シュート",
        "6": "奪取",
        "7": "守備",
        "8": "セーブ",
    }

    # 1. チームCBP比較テーブル
    for tbl in soup.find_all("table", class_=lambda c: c and "statsTbl6" in c):
        trs = tbl.find_all("tr")
        for i in range(len(trs) - 1):
            name_cell = [td.get_text(strip=True) for td in trs[i].find_all(["th", "td"]) if td.get_text(strip=True)]
            if len(name_cell) == 1 and name_cell[0] in category_names.values():
                val_cells = [td.get_text(strip=True) for td in trs[i + 1].find_all(["th", "td"]) if td.get_text(strip=True)]
                if len(val_cells) >= 5:
                    cbp_data["team"].append(
                        {
                            "name": name_cell[0],
                            "home_val": val_cells[1],
                            "home_avg": val_cells[0],
                            "away_val": val_cells[3],
                            "away_avg": val_cells[4],
                        },
                    )

    # 2. 選手別CBPランキング (rank1〜rank8)
    for cat_id, cat_name in category_names.items():
        rank_div = soup.find(id=f"rank{cat_id}")
        players_list = []
        if rank_div:
            tbl = rank_div.find("table")
            if tbl:
                for tr in tbl.find_all("tr"):
                    tds = [td.get_text(strip=True) for td in tr.find_all(["th", "td"])]
                    # Home側選手 or Away側選手
                    home_player = tds[0] if len(tds) > 0 and tds[0] else ""
                    points = tds[2] if len(tds) > 2 and tds[2] else ""
                    away_player = tds[4] if len(tds) > 4 and tds[4] else ""
                    if points:
                        players_list.append(
                            {
                                "home_player": home_player,
                                "away_player": away_player,
                                "points": points,
                            },
                        )
        cbp_data["categories"][cat_name] = players_list

    return cbp_data


def extract_flab_timeline_blocks(soup: BeautifulSoup) -> list[dict]:
    """15分刻みのポゼッション率とスタイル傾向を抽出する。"""
    timeline_blocks = []
    # タイムラインテーブル（クラスなしのテーブルで 00-15 等を含むもの）
    for tbl in soup.find_all("table"):
        text = tbl.get_text()
        if "00-15" in text or "46-60" in text:
            trs = tbl.find_all("tr")
            for i, tr in enumerate(trs):
                txt = tr.get_text(strip=True)
                period_match = re.search(r"(\d{2}-\d{2})", txt)
                if period_match and i + 2 < len(trs):
                    period = period_match.group(1)
                    # 次の行: ポゼッション率
                    pos_cells = [td.get_text(strip=True) for td in trs[i + 1].find_all(["th", "td"])]
                    home_pos = pos_cells[0] if len(pos_cells) > 0 else ""
                    away_pos = pos_cells[2] if len(pos_cells) > 2 else ""

                    # 2行先: スタイル
                    style_cells = [td.get_text(strip=True) for td in trs[i + 3].find_all(["th", "td"])] if i + 3 < len(trs) else []
                    home_style = style_cells[0] if len(style_cells) > 0 else ""
                    away_style = style_cells[2] if len(style_cells) > 2 else ""

                    timeline_blocks.append(
                        {
                            "period": period,
                            "home_possession": home_pos,
                            "away_possession": away_pos,
                            "home_style": home_style,
                            "away_style": away_style,
                        },
                    )

    return timeline_blocks


def extract_flab_script_data(html: str) -> dict:
    """インラインスクリプトから攻撃フローグラフデータおよびシュート位置データを抽出する。"""
    result = {
        "stream_1st": [],
        "stream_2nd": [],
        "home_shots": [],
        "away_shots": [],
    }

    # 前半攻撃フロー
    stream1_match = re.findall(
        r"drawChart\(\)\s*\{.*?arrayToDataTable\(\[\s*\['min\.', 'Home', 'Away'\],(.*?)\s*\]\);",
        html,
        re.DOTALL,
    )
    if stream1_match:
        points = re.findall(r"\[(\d+),\s*(-?\d+),\s*(-?\d+)\]", stream1_match[0])
        result["stream_1st"] = [
            {
                "min": int(p[0]),
                "home": int(p[1]),
                "away": int(p[2]),
            }
            for p in points
        ]

    # 後半攻撃フロー
    stream2_match = re.findall(
        r"drawChart2\(\)\s*\{.*?arrayToDataTable\(\[\s*\['min\.', 'Home', 'Away'\],(.*?)\s*\]\);",
        html,
        re.DOTALL,
    )
    if stream2_match:
        points = re.findall(r"\[(\d+),\s*(-?\d+),\s*(-?\d+)\]", stream2_match[0])
        result["stream_2nd"] = [
            {
                "min": int(p[0]),
                "home": int(p[1]),
                "away": int(p[2]),
            }
            for p in points
        ]

    # シュート位置 (HOME: drawShot, AWAY: drawShot2)
    shots_from = re.findall(
        r"fromData\s*=\s*google\.visualization\.arrayToDataTable\(\[\s*\['x', 'y'\],(.*?)\s*\]\);",
        html,
        re.DOTALL,
    )
    shots_to = re.findall(
        r"toData\s*=\s*google\.visualization\.arrayToDataTable\(\[\s*\['x', 'y'\],(.*?)\s*\]\);",
        html,
        re.DOTALL,
    )

    if len(shots_from) >= 1 and len(shots_to) >= 1:
        c_from = re.findall(r"\[([\d\.]+),\s*([\d\.]+)\]", shots_from[0])
        c_to = re.findall(r"\[([\d\.]+),\s*([\d\.]+)\]", shots_to[0])
        for i in range(min(len(c_from), len(c_to))):
            result["home_shots"].append(
                {
                    "from_x": float(c_from[i][0]),
                    "from_y": float(c_from[i][1]),
                    "to_x": float(c_to[i][0]),
                    "to_y": float(c_to[i][1]),
                },
            )

    if len(shots_from) >= 2 and len(shots_to) >= 2:
        c_from2 = re.findall(r"\[([\d\.]+),\s*([\d\.]+)\]", shots_from[1])
        c_to2 = re.findall(r"\[([\d\.]+),\s*([\d\.]+)\]", shots_to[1])
        for i in range(min(len(c_from2), len(c_to2))):
            result["away_shots"].append(
                {
                    "from_x": float(c_from2[i][0]),
                    "from_y": float(c_from2[i][1]),
                    "to_x": float(c_to2[i][0]),
                    "to_y": float(c_to2[i][1]),
                },
            )

    return result


def extract_flab_heatmaps(soup: BeautifulSoup) -> list[dict]:
    """前半/後半 × HOME/AWAYのヒートマップ（54分割グリッド）を抽出する。"""
    heatmaps = []
    titles = [
        "前半 HOME (FC東京)",
        "前半 AWAY",
        "後半 HOME (FC東京)",
        "後半 AWAY",
    ]

    hotzones = soup.find_all("table", class_=lambda c: c and "hotzone" in c)
    for i, hz in enumerate(hotzones):
        title = titles[i] if i < len(titles) else f"Hotzone {i}"
        grid = []
        for tr in hz.find_all("tr"):
            row = []
            for td in tr.find_all("td"):
                style = td.get("style", "")
                # rgba(r,g,b,alpha) から alpha（活動密度）を取得
                alpha_match = re.search(r"rgba\([^,]+,[^,]+,[^,]+,([\d\.]+)\)", style)
                density = float(alpha_match.group(1)) if alpha_match else 0.60
                row.append(round(density, 2))
            if row:
                grid.append(row)

        heatmaps.append(
            {
                "title": title,
                "grid": grid,
            },
        )

    return heatmaps


def extract_flab_team_style(soup: BeautifulSoup) -> list[dict]:
    """サマリーページからチームスタイル指標（攻撃・守備の傾向）を抽出する。"""
    styles = []
    style_links = soup.find_all("a", href=lambda h: h and "/style/?s=" in h)
    for a in style_links:
        txt = a.get_text(strip=True)
        # 例: 中央攻撃6331.8% -> 指数63, 割合31.8%
        match = re.search(r"^(.+?)(\d{2})(\d{1,2}\.\d)%$", txt)
        if match:
            styles.append(
                {
                    "name": match.group(1),
                    "index": match.group(2),
                    "percentage": f"{match.group(3)}%",
                },
            )
        else:
            styles.append(
                {
                    "name": txt,
                    "index": "-",
                    "percentage": "-",
                },
            )

    return styles


def format_players_table(players: list[dict]) -> str:
    """選手リストをMarkdownテーブルに整形する。"""
    if not players:
        return "データなし"

    lines = [
        "| ポジション | 背番号 | 選手名 | 出場時間 | 交代 | カード |",
        "| :---: | :---: | :--- | :---: | :---: | :---: |",
    ]
    for p in players:
        lines.append(
            f"| {p.get('position', '-')} | {p.get('number', '-')} | {p.get('name', '-')} | {p.get('minutes', '-')} | {p.get('change', '-')} | {p.get('card', '-')} |",
        )
    return "\n".join(lines)


def format_stats_table(stats: list[dict]) -> str:
    """全スタッツをMarkdownテーブルに整形する。"""
    if not stats:
        return "スタッツ集計中（データ未反映）"

    lines = [
        "| 指標 | HOME (実数) | (成功率) | AWAY (実数) | (成功率) | 今季平均(H) | 今季平均(A) |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    for s in stats:
        lines.append(
            f"| {s['name']} | {s['home_val']} | {s['home_rate']} | {s['away_val']} | {s['away_rate']} | {s['home_avg']} | {s['away_avg']} |",
        )
    return "\n".join(lines)


def format_cbp_markdown(cbp_data: dict) -> str:
    """CBPチーム比較および各カテゴリ選手ランキングをMarkdownに整形する。"""
    lines = ["### チーム比較 (合計 & 平均)", ""]
    if cbp_data["team"]:
        lines.append("| 指標 | HOME (実数) | (今季平均) | AWAY (実数) | (今季平均) |")
        lines.append("| :--- | :---: | :---: | :---: | :---: |")
        for t in cbp_data["team"]:
            lines.append(f"| {t['name']} | {t['home_val']} | {t['home_avg']} | {t['away_val']} | {t['away_avg']} |")
        lines.append("")
    else:
        lines.append("チームCBPデータなし\n")

    lines.append("### カテゴリ別 選手獲得ポイント")
    for cat_name, players in cbp_data["categories"].items():
        lines.append(f"#### 【{cat_name}】")
        if players:
            lines.append("| HOME選手 | AWAY選手 | ポイント |")
            lines.append("| :--- | :--- | :---: |")
            for p in players[:10]:  # トップ10名
                lines.append(f"| {p['home_player'] or '-'} | {p['away_player'] or '-'} | {p['points']} |")
            lines.append("")
        else:
            lines.append("データなし\n")

    return "\n".join(lines)


def build_flab_markdown(
    match_id: str,
    url: str,
    title: str,
    report_text: str,
    players_data: dict,
    stats: list[dict],
    cbp_data: dict,
    timeline_blocks: list[dict],
    script_data: dict,
    heatmaps: list[dict],
    team_styles: list[dict],
) -> str:
    """Football LABの全データを統合した構造化Markdownを生成する。"""
    home_name = players_data["home"]["name"]
    away_name = players_data["away"]["name"]

    home_starting_md = format_players_table(players_data["home"]["starting"])
    home_subs_md = format_players_table(players_data["home"]["substitutes"])
    away_starting_md = format_players_table(players_data["away"]["starting"])
    away_subs_md = format_players_table(players_data["away"]["substitutes"])

    stats_md = format_stats_table(stats)
    cbp_md = format_cbp_markdown(cbp_data)

    lines = [
        f"# {title} (Match ID: {match_id})",
        "",
        "## 【1. 基本情報・戦評】",
        f"- **対象URL**: {url}",
        "- **情報ソース**: Football LAB (フットボールラボ) / J.LEAGUE Data Site",
        "",
        "### 公式戦評",
        report_text,
        "",
        "## 【2. 出場選手・ポジション・出場時間・カード】",
        f"### {home_name} (HOME)",
        f"- **監督**: {players_data['home']['coach'] or '未登録'}",
        "#### スターティングメンバー",
        home_starting_md,
        "",
        "#### ベンチメンバー",
        home_subs_md,
        "",
        f"### {away_name} (AWAY)",
        f"- **監督**: {players_data['away']['coach'] or '未登録'}",
        "#### スターティングメンバー",
        away_starting_md,
        "",
        "#### ベンチメンバー",
        away_subs_md,
        "",
        "## 【3. チーム全スタッツ比較 (xG・トラッキング・進入数・保持率等)】",
        stats_md,
        "",
        "## 【4. チャンスビルディングポイント (CBP)】",
        cbp_md,
        "",
        "## 【5. タイムライン・攻撃フローグラフデータ】",
        "### 15分刻みポゼッション & 主要スタイル傾向",
    ]

    if timeline_blocks:
        lines.append("| 時間帯 | HOME保持率 | AWAY保持率 | HOMEスタイル | AWAYスタイル |")
        lines.append("| :---: | :---: | :---: | :--- | :--- |")
        for b in timeline_blocks:
            lines.append(
                f"| {b['period']}分 | {b['home_possession']} | {b['away_possession']} | {b['home_style']} | {b['away_style']} |",
            )
        lines.append("")
    else:
        lines.append("タイムライン集計なし\n")

    lines.append("### 分刻み攻撃フロー推移（折れ線グラフ実数値データ）")
    if script_data["stream_1st"]:
        s1_str = ", ".join([f"[{p['min']}分: +{p['home']}/-{abs(p['away'])}]" for p in script_data["stream_1st"][:20]])
        lines.append(f"- **前半 (0〜50分抜粋)**: {s1_str} ... (計{len(script_data['stream_1st'])}点)")
    if script_data["stream_2nd"]:
        s2_str = ", ".join([f"[{p['min']}分: +{p['home']}/-{abs(p['away'])}]" for p in script_data["stream_2nd"][:20]])
        lines.append(f"- **後半 (0〜50分抜粋)**: {s2_str} ... (計{len(script_data['stream_2nd'])}点)")
    lines.append("")

    lines.append("## 【6. シュート位置データ (ピッチ座標)】")
    lines.append(f"- **{home_name} (HOME)**: 計 {len(script_data['home_shots'])} 本")
    for idx, s in enumerate(script_data["home_shots"][:10], 1):
        lines.append(f"  - [{idx}] 発射位置: ({s['from_x']}, {s['from_y']}) -> 到達位置: ({s['to_x']}, {s['to_y']})")
    if len(script_data["home_shots"]) > 10:
        lines.append(f"  - ...他 {len(script_data['home_shots']) - 10} 本")

    lines.append(f"- **{away_name} (AWAY)**: 計 {len(script_data['away_shots'])} 本")
    for idx, s in enumerate(script_data["away_shots"][:10], 1):
        lines.append(f"  - [{idx}] 発射位置: ({s['from_x']}, {s['from_y']}) -> 到達位置: ({s['to_x']}, {s['to_y']})")
    if len(script_data["away_shots"]) > 10:
        lines.append(f"  - ...他 {len(script_data['away_shots']) - 10} 本")
    lines.append("")

    lines.append("## 【7. ヒートマップ (ピッチ54分割エリア活動密度)】")
    for hz in heatmaps:
        lines.append(f"### {hz['title']}")
        if hz["grid"]:
            lines.append("（6行×9列の自陣ゴール側〜相手ゴール側エリア密度 [0.60(低)〜1.00(高)]）")
            for row in hz["grid"]:
                row_str = " | ".join([f"{v:.2f}" for v in row])
                lines.append(f"| {row_str} |")
        lines.append("")

    lines.append("## 【8. チームスタイル指標（最新シーズン傾向）】")
    if team_styles:
        lines.append("| スタイル指標 | 指数 | 発生割合 |")
        lines.append("| :--- | :---: | :---: |")
        for st in team_styles:
            lines.append(f"| {st['name']} | {st['index']} | {st['percentage']} |")
        lines.append("")
    else:
        lines.append("チームスタイルデータなし\n")

    return "\n".join(lines)


def scrape_football_lab_match(
    match_id: str,
    match_url: str,
    club_summary_url: str = "https://www.football-lab.jp/fctk/",
    output_dir: str = "data/markdown",
) -> str:
    """Football LABから試合データおよびチームスタイルをスクレイピングしてMarkdownに保存する。"""
    print(f"[{match_id}] Football LABのスクレイピングを開始します: {match_url}")

    match_html = fetch_html(match_url)
    match_soup = BeautifulSoup(match_html, "html.parser")

    title_elem = match_soup.find("title")
    title = title_elem.get_text(strip=True).split("|")[0].strip() if title_elem else f"Match {match_id}"

    # 各項目抽出
    report_text = extract_flab_report_text(match_soup)
    players_data = extract_flab_players(match_soup)
    stats = extract_flab_stats(match_soup)
    cbp_data = extract_flab_cbp(match_soup)
    timeline_blocks = extract_flab_timeline_blocks(match_soup)
    script_data = extract_flab_script_data(match_html)
    heatmaps = extract_flab_heatmaps(match_soup)

    # チームスタイル指標（クラブサマリーより）
    print(f"  -> チームスタイルを取得中: {club_summary_url}")
    summary_html = fetch_html(club_summary_url)
    summary_soup = BeautifulSoup(summary_html, "html.parser")
    team_styles = extract_flab_team_style(summary_soup)

    markdown_content = build_flab_markdown(
        match_id=match_id,
        url=match_url,
        title=title,
        report_text=report_text,
        players_data=players_data,
        stats=stats,
        cbp_data=cbp_data,
        timeline_blocks=timeline_blocks,
        script_data=script_data,
        heatmaps=heatmaps,
        team_styles=team_styles,
    )

    os.makedirs(output_dir, exist_ok=True)
    file_path = os.path.join(output_dir, f"{match_id}_flab.md")

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(markdown_content)

    print(f"成功: Football LABデータを {file_path} に保存しました。\n")
    return file_path


if __name__ == "__main__":
    # 10/21 柏戦（全スタッツ・トラッキング・CBPが反映済みの試合）
    sample_match_id = "20261021_FCT_KAS"
    sample_url = "https://www.football-lab.jp/fctk/report/?year=2026&month=10&date=21"
    scrape_football_lab_match(sample_match_id, sample_url)
