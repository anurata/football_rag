import json
import os
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

JLEAGUE_BASE_URL = "https://www.jleague.jp"

# J1 2026シーズン 20クラブのスラッグ・IDマッピング
J1_CLUBS_2026 = [
    {
        "team_id": "KAS",
        "club_slug": "kashima",
        "club_name": "鹿島アントラーズ",
    },
    {
        "team_id": "MIT",
        "club_slug": "mito",
        "club_name": "水戸ホーリーホック",
    },
    {
        "team_id": "URA",
        "club_slug": "urawa",
        "club_name": "浦和レッズ",
    },
    {
        "team_id": "JEF",
        "club_slug": "chiba",
        "club_name": "ジェフユナイテッド千葉",
    },
    {
        "team_id": "REY",
        "club_slug": "kashiwa",
        "club_name": "柏レイソル",
    },
    {
        "team_id": "FCT",
        "club_slug": "ftokyo",
        "club_name": "ＦＣ東京",
    },
    {
        "team_id": "VER",
        "club_slug": "tokyov",
        "club_name": "東京ヴェルディ",
    },
    {
        "team_id": "ZEL",
        "club_slug": "machida",
        "club_name": "ＦＣ町田ゼルビア",
    },
    {
        "team_id": "KAW",
        "club_slug": "kawasakif",
        "club_name": "川崎フロンターレ",
    },
    {
        "team_id": "MAR",
        "club_slug": "yokohamafm",
        "club_name": "横浜Ｆ・マリノス",
    },
    {
        "team_id": "PUL",
        "club_slug": "shimizu",
        "club_name": "清水エスパルス",
    },
    {
        "team_id": "NAG",
        "club_slug": "nagoya",
        "club_name": "名古屋グランパス",
    },
    {
        "team_id": "KYO",
        "club_slug": "kyoto",
        "club_name": "京都サンガF.C.",
    },
    {
        "team_id": "GAM",
        "club_slug": "gosaka",
        "club_name": "ガンバ大阪",
    },
    {
        "team_id": "CER",
        "club_slug": "cosaka",
        "club_name": "セレッソ大阪",
    },
    {
        "team_id": "VOB",
        "club_slug": "kobe",
        "club_name": "ヴィッセル神戸",
    },
    {
        "team_id": "OKA",
        "club_slug": "okayama",
        "club_name": "ファジアーノ岡山",
    },
    {
        "team_id": "SAN",
        "club_slug": "hiroshima",
        "club_name": "サンフレッチェ広島",
    },
    {
        "team_id": "FUK",
        "club_slug": "fukuoka",
        "club_name": "アビスパ福岡",
    },
    {
        "team_id": "VVN",
        "club_slug": "nagasaki",
        "club_name": "Ｖ・ファーレン長崎",
    },
]


def extract_player_id_from_url(url: str) -> str:
    """URLから選手ID（例: 1632774）を抽出する。"""
    match = re.search(r"/player/(\d+)/?", url)
    if match:
        return match.group(1)
    return ""


def clean_text(text: Optional[str]) -> str:
    """テキストの前後の空白や特殊文字をクリーンアップする。"""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def parse_player_table_row(tr_el) -> Optional[Dict[str, Any]]:
    """選手一覧テーブルの1行（tr）から基本情報をパースする。"""
    a_link = tr_el.find("a", href=re.compile(r"^/player/\d+/?"))
    if not a_link:
        return None

    detail_href = a_link.get("href", "")
    player_id = extract_player_id_from_url(detail_href)
    name = clean_text(a_link.get_text(strip=True))

    # サムネイル画像
    img = tr_el.find("img")
    thumb_src = img.get("src", "") if img else ""
    if thumb_src and not thumb_src.startswith("http"):
        thumb_src = urljoin(JLEAGUE_BASE_URL, thumb_src)

    # ポジションと背番号（例: 'DF 2' や 'FW 26'）
    pos_el = tr_el.find(class_=lambda c: c and "o-table__player-position" in c)
    position = ""
    number = ""
    if pos_el:
        pos_parts = pos_el.get_text(strip=True).split()
        if len(pos_parts) >= 2:
            position = pos_parts[0]
            number = pos_parts[1]
        elif len(pos_parts) == 1:
            position = pos_parts[0]

    # カラムデータ（出身地、生年月日、身長/体重、出場数、得点数）
    cols = tr_el.find_all("td")
    birthplace = ""
    birthdate = ""
    height_cm = ""
    weight_kg = ""
    matches = "0"
    goals = "0"

    if len(cols) >= 1:
        birthplace = clean_text(cols[0].get_text(strip=True))
    if len(cols) >= 2:
        birthdate = clean_text(cols[1].get_text(strip=True))
    if len(cols) >= 3:
        hw_text = clean_text(cols[2].get_text(strip=True))
        hw_match = re.search(r"(\d+)\s*/\s*(\d+)", hw_text)
        if hw_match:
            height_cm = hw_match.group(1)
            weight_kg = hw_match.group(2)
    if len(cols) >= 4:
        matches = clean_text(cols[3].get_text(strip=True))
    if len(cols) >= 5:
        goals = clean_text(cols[4].get_text(strip=True))

    return {
        "player_id": player_id,
        "name": name,
        "position": position,
        "number": number,
        "thumbnail_url": thumb_src,
        "detail_url": urljoin(JLEAGUE_BASE_URL, detail_href),
        "birthplace": birthplace,
        "birthdate": birthdate,
        "height_cm": height_cm,
        "weight_kg": weight_kg,
        "matches": matches,
        "goals": goals,
    }


def parse_club_players_html(html: str) -> List[Dict[str, Any]]:
    """クラブ選手一覧ページのHTMLから全所属選手リストを抽出する。"""
    soup = BeautifulSoup(html, "html.parser")
    players = []
    seen_ids = set()

    for tr in soup.find_all("tr"):
        p_data = parse_player_table_row(tr)
        if p_data and p_data["player_id"] and p_data["player_id"] not in seen_ids:
            seen_ids.add(p_data["player_id"])
            players.append(p_data)

    return players


def extract_header_profile(soup: BeautifulSoup) -> Dict[str, str]:
    """選手詳細ヘッダーから名前、英名、背番号、ポジション、所属クラブ、画像URLを抽出する。"""
    header = soup.find(class_=lambda c: c and "o-page-header--player-details" in c)
    info = {
        "club_name": "",
        "position": "",
        "number": "",
        "name": "",
        "name_en": "",
        "photo_url": "",
    }

    if not header:
        return info

    club_el = header.find(class_=lambda c: c and "o-page-header__name-club" in c)
    if club_el:
        info["club_name"] = clean_text(club_el.get_text(strip=True))

    pos_el = header.find(class_=lambda c: c and "o-page-header__name-position" in c)
    if pos_el:
        parts = pos_el.get_text(strip=True).split()
        if len(parts) >= 2:
            info["position"] = parts[0]
            info["number"] = parts[1]
        elif len(parts) == 1:
            info["position"] = parts[0]

    name_el = header.find(class_=lambda c: c and "o-page-header__name" == c.strip())
    if name_el:
        info["name"] = clean_text(name_el.get_text(strip=True))

    name_en_el = header.find(class_=lambda c: c and "o-page-header__name-en" in c)
    if name_en_el:
        info["name_en"] = clean_text(name_en_el.get_text(strip=True))

    # メイン顔写真画像（_l.webp）
    img = None
    if header:
        for im in header.find_all("img"):
            src = im.get("src", "")
            if "player" in src and ("_l.webp" in src or "main" in src):
                img = im
                break

    if not img:
        img = soup.find("img", src=re.compile(r"/player/.*/\d+_l\.webp"))

    if not img:
        for im in soup.find_all("img"):
            src = im.get("src", "")
            if "_l.webp" in src or "player/main" in src:
                img = im
                break

    if img:
        src = img.get("src", "")
        info["photo_url"] = urljoin(JLEAGUE_BASE_URL, src)

    return info


def extract_info_list(soup: BeautifulSoup) -> Dict[str, str]:
    """基本情報リスト（出身地、生年月日、初出場等）を抽出する。"""
    data = {
        "birthplace": "",
        "birthdate": "",
        "height_cm": "",
        "weight_kg": "",
        "jleague_debut": "",
        "jleague_first_goal": "",
        "national_team_caps": "",
    }

    for item in soup.find_all(class_=lambda c: c and "p-player-details__info-item" in c):
        p_tags = item.find_all("p")
        if len(p_tags) >= 2:
            label = clean_text(p_tags[0].get_text(strip=True))
            val = clean_text(p_tags[1].get_text(strip=True))

            if "出身地" in label:
                data["birthplace"] = val
            elif "生年月日" in label:
                data["birthdate"] = val
            elif "身長" in label or "体重" in label:
                hw = re.search(r"(\d+)cm/(\d+)kg", val)
                if hw:
                    data["height_cm"] = hw.group(1)
                    data["weight_kg"] = hw.group(2)
            elif "初出場" in label:
                data["jleague_debut"] = val
            elif "初得点" in label:
                data["jleague_first_goal"] = val
            elif "代表" in label:
                data["national_team_caps"] = val

    return data


def extract_season_stats(soup: BeautifulSoup) -> Dict[str, Any]:
    """レーダー・平均スタッツ比較から当該シーズンの主要スタッツ数値を抽出する。"""
    stats = {}
    details = soup.find_all(class_=lambda c: c and "m-player-stats__detail" == c.strip())
    for d in details:
        name_el = d.find(class_=lambda c: c and "m-player-stats__detail-name" in c)
        num_el = d.find(class_=lambda c: c and "m-player-stats__detail-number" in c)
        if name_el and num_el:
            label = clean_text(name_el.get_text(strip=True))
            raw_val = clean_text(num_el.get_text(strip=True)).replace("km", "").strip()
            try:
                num_val: Any = float(raw_val) if "." in raw_val else int(raw_val)
            except ValueError:
                num_val = raw_val
            stats[label] = num_val

    return stats


def extract_career_history(soup: BeautifulSoup) -> List[Dict[str, str]]:
    """キャリア（過去所属クラブ履歴・期限付き移籍等）テーブルを抽出する。"""
    history = []
    career_sec = soup.find(class_=lambda c: c and "p-player-profile__career" in c)
    if not career_sec:
        # 見出しから探索
        for h in soup.find_all(["h1", "h2", "h3"]):
            if "キャリア" in h.get_text(strip=True):
                career_sec = h.find_parent("section") or h.find_parent("div")
                break

    if not career_sec:
        return history

    for tr in career_sec.find_all("tr"):
        cols = [clean_text(td.get_text(strip=True)) for td in tr.find_all("td")]
        if len(cols) >= 3:
            history.append(
                {
                    "season": cols[0],
                    "club": cols[1],
                    "league": cols[2],
                    "league_matches": cols[3] if len(cols) > 3 else "-",
                    "league_goals": cols[4] if len(cols) > 4 else "-",
                },
            )

    return history


def evaluate_strong_points(
    stats: Dict[str, Any],
    position: str,
    height_cm: str = "",
) -> List[str]:
    """
    客観スタッツおよびフィジカル数値から、選手のストロングポイント・強みを決定論的に判定する。
    """
    strong_points = []

    # スプリント能力
    sprint_count = stats.get("総スプリント回数", 0)
    if isinstance(sprint_count, (int, float)) and sprint_count >= 150:
        strong_points.append(
            f"卓越したスプリント力（シーズン{sprint_count}回）による背後へのラインブレイクと推進力",
        )

    # チャンスクリエイト能力
    cc_count = stats.get("チャンスクリエイト総数", 0)
    if isinstance(cc_count, (int, float)) and cc_count >= 15:
        strong_points.append(
            f"決定機を演出する高精度なラストパスとチャンスメイク力（{cc_count}回）",
        )

    # 枠内シュート・フィニッシュ精度
    shots = stats.get("枠内シュート総数", 0)
    if isinstance(shots, (int, float)) and shots >= 10:
        strong_points.append(
            f"積極的なアタッキングサード侵入と枠内シュート精度（{shots}本）",
        )

    # デュエル・球際の強さ
    duels = stats.get("デュエル勝利総数", 0)
    if isinstance(duels, (int, float)) and duels >= 15:
        strong_points.append(
            f"局面での球際の強さと地上デュエル勝率（勝利数{duels}回）",
        )

    # 走行距離・運動量
    dist = stats.get("総走行距離", 0)
    if isinstance(dist, (int, float)) and dist >= 100:
        strong_points.append(
            f"90分間ピッチを広くカバーする豊富な運動量とハードワーク（総走行距離{dist}km）",
        )

    # 空中戦・ターゲット能力
    aerial = stats.get("空中戦勝利数", 0)
    if isinstance(aerial, (int, float)) and aerial >= 10:
        if position == "GK":
            strong_points.append(
                f"ハイボール処理とクロス対応の制空権（空中戦{aerial}勝）",
            )
        elif position == "DF":
            strong_points.append(
                f"相手FWとの制空権争いに勝る空中戦の強さ（{aerial}勝）",
            )
        else:
            strong_points.append(
                f"前線での空中戦・ハイボール競り合いに強いターゲットマンとしての強さ（{aerial}勝）",
            )
    elif height_cm.isdigit() and int(height_cm) >= 185:
        if position == "GK":
            strong_points.append(
                f"身長{height_cm}cmの体格を活かしたハイボール処理とゴール前の威圧感",
            )
        elif position == "DF":
            strong_points.append(
                f"身長{height_cm}cmの高さを活かした空中戦とセットプレーでの競り合いの強さ",
            )
        else:
            strong_points.append(
                f"身長{height_cm}cmの高さを活かした空中戦とポストプレーの起点",
            )

    # ポジション特性によるベースポイント
    if not strong_points:
        if position == "FW":
            strong_points.append("ゴール前でのポジショニングと前線からのハイプレス")
        elif position == "MF":
            strong_points.append("中盤でのリンクマンとしての配球と攻守の切り替え")
        elif position == "DF":
            strong_points.append("カバーリング能力と対人守備の安定感")
        elif position == "GK":
            strong_points.append("シュートストップとディフェンスラインの統率")

    return strong_points


def load_dominant_foot_master(config_path: str = "config/player_dominant_foot.json") -> Dict[str, str]:
    """利き足マスタ辞書を読み込む。"""
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("players", {})
        except Exception:
            return {}
    return {}


def determine_dominant_foot(player_name: str, foot_master: Dict[str, str]) -> str:
    """選手名から利き足を判定する。マスタに存在しない場合は空文字を返す。"""
    if player_name in foot_master:
        return foot_master[player_name]
    # 名前の表記ゆれ（空白除去）でマッチング
    clean_pname = player_name.replace(" ", "").replace("　", "")
    for k, v in foot_master.items():
        if k.replace(" ", "").replace("　", "") == clean_pname:
            return v
    return ""


def parse_player_detail_html(
    html: str,
    player_id: str = "",
    foot_master: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """選手個別ページのHTMLから全詳細情報を統合して辞書化する。"""
    soup = BeautifulSoup(html, "html.parser")

    header_info = extract_header_profile(soup)
    basic_info = extract_info_list(soup)
    season_stats = extract_season_stats(soup)
    career_history = extract_career_history(soup)

    p_name = header_info.get("name", "")
    pos = header_info.get("position", "")
    h_cm = basic_info.get("height_cm", "")
    strong_points = evaluate_strong_points(
        stats=season_stats,
        position=pos,
        height_cm=h_cm,
    )

    dominant_foot = ""
    if foot_master:
        dominant_foot = determine_dominant_foot(p_name, foot_master)

    detail_data = {
        "player_id": player_id,
        "name": p_name,
        "name_en": header_info.get("name_en", ""),
        "club_name": header_info.get("club_name", ""),
        "position": pos,
        "number": header_info.get("number", ""),
        "dominant_foot": dominant_foot,
        "photo_url": header_info.get("photo_url", ""),
        "birthplace": basic_info.get("birthplace", ""),
        "birthdate": basic_info.get("birthdate", ""),
        "height_cm": h_cm,
        "weight_kg": basic_info.get("weight_kg", ""),
        "jleague_debut": basic_info.get("jleague_debut", ""),
        "jleague_first_goal": basic_info.get("jleague_first_goal", ""),
        "national_team_caps": basic_info.get("national_team_caps", "0"),
        "season_stats": season_stats,
        "strong_points": strong_points,
        "career_history": career_history,
    }

    return detail_data


class JLeaguePlayerScraper:
    """Jリーグ公式サイトから選手名鑑データを収集・構造化するスクレイパークラス。"""

    def __init__(
        self,
        output_dir: str = "data/players",
        rate_limit_sec: float = 0.8,
        foot_master_path: str = "config/player_dominant_foot.json",
    ):
        self.output_dir = output_dir
        self.rate_limit_sec = rate_limit_sec
        self.foot_master = load_dominant_foot_master(foot_master_path)
        os.makedirs(self.output_dir, exist_ok=True)

    def fetch_club_players_list(
        self,
        club_slug: str,
        page,
    ) -> List[Dict[str, Any]]:
        """クラブの選手一覧ページにアクセスし、所属選手リストを取得する。"""
        url = f"{JLEAGUE_BASE_URL}/club/{club_slug}/?navicode=j1#player"
        print(f"  -> クラブ選手一覧を取得中: {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)

        # 選手一覧タブがあればクリックして開く
        for tab in page.query_selector_all("a, button, li"):
            if "選手一覧" in tab.inner_text().strip():
                try:
                    tab.click()
                    page.wait_for_timeout(1500)
                except Exception:
                    pass
                break

        html = page.content()
        return parse_club_players_html(html)

    def fetch_player_detail(
        self,
        player_id: str,
        page,
    ) -> Dict[str, Any]:
        """選手個別ページにアクセスし、詳細情報を取得する。"""
        url = f"{JLEAGUE_BASE_URL}/player/{player_id}/"
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1000)

        html = page.content()
        detail = parse_player_detail_html(
            html=html,
            player_id=player_id,
            foot_master=self.foot_master,
        )
        return detail

    def scrape_team(
        self,
        team_id: str,
        club_slug: str,
        page,
        max_players: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """特定クラブの全選手データをスクレイピングして統合する。"""
        print(f"[{team_id}] {club_slug} の選手データ取得を開始します...")
        base_players = self.fetch_club_players_list(club_slug, page)
        print(f"  -> 所属選手 {len(base_players)} 名を検出しました。")

        target_players = base_players[:max_players] if max_players else base_players
        full_players = []

        for i, bp in enumerate(target_players):
            pid = bp["player_id"]
            pname = bp["name"]
            print(f"    ({i + 1}/{len(target_players)}) {pname} (ID: {pid}) の詳細を取得中...")

            try:
                detail = self.fetch_player_detail(pid, page)
                # 基本一覧データと詳細データをマージ
                merged = {
                    "player_id": pid,
                    "team_id": team_id,
                    "name": detail.get("name") or bp["name"],
                    "name_en": detail.get("name_en", ""),
                    "club_name": detail.get("club_name") or bp.get("club_name", ""),
                    "position": detail.get("position") or bp["position"],
                    "number": detail.get("number") or bp["number"],
                    "dominant_foot": detail.get("dominant_foot") or determine_dominant_foot(bp["name"], self.foot_master),
                    "photo_url": detail.get("photo_url") or bp["thumbnail_url"],
                    "thumbnail_url": bp["thumbnail_url"],
                    "birthplace": detail.get("birthplace") or bp["birthplace"],
                    "birthdate": detail.get("birthdate") or bp["birthdate"],
                    "height_cm": detail.get("height_cm") or bp["height_cm"],
                    "weight_kg": detail.get("weight_kg") or bp["weight_kg"],
                    "matches": bp.get("matches", "0"),
                    "goals": bp.get("goals", "0"),
                    "jleague_debut": detail.get("jleague_debut", ""),
                    "jleague_first_goal": detail.get("jleague_first_goal", ""),
                    "national_team_caps": detail.get("national_team_caps", "0"),
                    "strong_points": detail.get("strong_points", []),
                    "season_stats": detail.get("season_stats", {}),
                    "career_history": detail.get("career_history", []),
                }
                full_players.append(merged)
            except Exception as e:
                print(f"    [警告] 選手ID {pid} の詳細取得に失敗しました: {e}")
                # 基本情報だけでも保存
                bp["team_id"] = team_id
                bp["dominant_foot"] = determine_dominant_foot(bp["name"], self.foot_master)
                bp["strong_points"] = evaluate_strong_points(
                    stats={},
                    position=bp["position"],
                    height_cm=bp["height_cm"],
                )
                full_players.append(bp)

            time.sleep(self.rate_limit_sec)

        # チームJSONの保存
        team_file = os.path.join(self.output_dir, f"{team_id}_players.json")
        with open(team_file, "w", encoding="utf-8") as f:
            json.dump(full_players, f, ensure_ascii=False, indent=2)

        print(f"[{team_id}] 保存完了: {len(full_players)} 名の選手データを {team_file} に保存しました。\n")
        return full_players


def run_pipeline(
    teams: Optional[List[Dict[str, str]]] = None,
    max_players_per_team: Optional[int] = None,
    output_dir: str = "data/players",
    headless: bool = True,
):
    """J1全チームまたは指定チームの選手名鑑スクレイピングを実行する。"""
    from playwright.sync_api import sync_playwright

    target_clubs = teams or J1_CLUBS_2026
    scraper = JLeaguePlayerScraper(output_dir=output_dir)
    all_players = []

    print(f"=== Jリーグ選手名鑑スクレイピング開始 (対象: {len(target_clubs)} チーム) ===")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={
                "width": 1280,
                "height": 800,
            },
        )
        page = context.new_page()

        for c in target_clubs:
            tid = c["team_id"]
            slug = c["club_slug"]
            try:
                team_data = scraper.scrape_team(
                    team_id=tid,
                    club_slug=slug,
                    page=page,
                    max_players=max_players_per_team,
                )
                all_players.extend(team_data)
            except Exception as e:
                print(f"[エラー] チーム {tid} ({slug}) のスクレイピング中に失敗しました: {e}")

        browser.close()

    # 全選手統合JSONの保存
    all_file = os.path.join(output_dir, "all_players.json")
    with open(all_file, "w", encoding="utf-8") as f:
        json.dump(all_players, f, ensure_ascii=False, indent=2)

    print(f"=== 全体完了: 合計 {len(all_players)} 名の選手データを {all_file} に保存しました ===")


if __name__ == "__main__":
    # パイロットテスト: FC東京から3選手を取得して検証
    fctokyo_club = [{"team_id": "FCT", "club_slug": "ftokyo", "club_name": "ＦＣ東京"}]
    run_pipeline(teams=fctokyo_club, max_players_per_team=3)
