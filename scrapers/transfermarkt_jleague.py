"""Transfermarkt日本語版（transfermarkt.jp）およびWikipedia APIからのJ1選手属性スクレイパー.

J.LEAGUE.jp / Yahoo / Football LAB に存在しない以下のLayer 1客観属性を構造化取得する:
1. 利き足 (dominant_foot: 右足 / 左足 / 両足)
2. 詳細戦術ポジション (CB / LSB / RSB / DMF / CMF / OMF / RWG / LWG / ST / CF)
3. 期限付き移籍元クラブ (loan_from_club)・加入日・前所属クラブ・契約満了日・国籍・推定市場価値
4. J1全20クラブの負傷離脱者リスト (/verletztespieler)
5. 最新節の出場停止・警告リーチリスト (/sperrenausfaelle)
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup, Tag

logger = logging.getLogger("transfermarkt_jleague")

TM_BASE_URL = "https://www.transfermarkt.jp"
WIKI_API_URL = "https://ja.wikipedia.org/w/api.php"

J1_TM_CLUBS_2026: List[Dict[str, str]] = [
    {"team_id": "KAS", "tm_slug": "kashima-antlers", "verein_id": "2241", "club_name": "鹿島アントラーズ"},
    {"team_id": "MIT", "tm_slug": "mito-hollyhock", "verein_id": "21975", "club_name": "水戸ホーリーホック"},
    {"team_id": "URA", "tm_slug": "urawa-red-diamonds", "verein_id": "828", "club_name": "浦和レッズ"},
    {"team_id": "JEF", "tm_slug": "jef-united-chiba", "verein_id": "672", "club_name": "ジェフユナイテッド千葉"},
    {"team_id": "REY", "tm_slug": "kashiwa-reysol", "verein_id": "6632", "club_name": "柏レイソル"},
    {"team_id": "FCT", "tm_slug": "fc-tokyo", "verein_id": "6631", "club_name": "FC東京"},
    {"team_id": "VER", "tm_slug": "tokyo-verdy", "verein_id": "3734", "club_name": "東京ヴェルディ"},
    {"team_id": "ZEL", "tm_slug": "machida-zelvia", "verein_id": "23568", "club_name": "FC町田ゼルビア"},
    {"team_id": "KAW", "tm_slug": "kawasaki-frontale", "verein_id": "9598", "club_name": "川崎フロンターレ"},
    {"team_id": "MAR", "tm_slug": "yokohama-f-marinos", "verein_id": "3828", "club_name": "横浜F・マリノス"},
    {"team_id": "PUL", "tm_slug": "shimizu-s-pulse", "verein_id": "1062", "club_name": "清水エスパルス"},
    {"team_id": "NAG", "tm_slug": "nagoya-grampus", "verein_id": "1066", "club_name": "名古屋グランパス"},
    {"team_id": "SAN", "tm_slug": "kyoto-sanga", "verein_id": "593", "club_name": "京都サンガF.C."},
    {"team_id": "GAM", "tm_slug": "gamba-osaka", "verein_id": "596", "club_name": "ガンバ大阪"},
    {"team_id": "CER", "tm_slug": "cerezo-osaka", "verein_id": "1022", "club_name": "セレッソ大阪"},
    {"team_id": "VOB", "tm_slug": "vissel-kobe", "verein_id": "3958", "club_name": "ヴィッセル神戸"},
    {"team_id": "OKA", "tm_slug": "fagiano-okayama", "verein_id": "22171", "club_name": "ファジアーノ岡山"},
    {"team_id": "HIR", "tm_slug": "sanfrecce-hiroshima", "verein_id": "2697", "club_name": "サンフレッチェ広島"},
    {"team_id": "FUK", "tm_slug": "avispa-fukuoka", "verein_id": "9597", "club_name": "アビスパ福岡"},
    {"team_id": "VVN", "tm_slug": "v-varen-nagasaki", "verein_id": "23581", "club_name": "V・ファーレン長崎"},
]

VEREIN_TO_TEAM_ID: Dict[str, str] = {
    c["verein_id"]: c["team_id"] for c in J1_TM_CLUBS_2026
}

TM_POSITION_MAP: List[Tuple[str, str]] = [
    ("ゴールキーパー", "GK"),
    ("センターバック", "CB"),
    ("左サイドバック", "LSB"),
    ("右サイドバック", "RSB"),
    ("守備的ミッドフィルダー", "DMF"),
    ("守備的ミッドフィールダー", "DMF"),
    ("セントラルミッドフィルダー", "CMF"),
    ("セントラルミッドフィールダー", "CMF"),
    ("右ミッドフィルダー", "RMF"),
    ("右ミッドフィールダー", "RMF"),
    ("左ミッドフィルダー", "LMF"),
    ("左ミッドフィールダー", "LMF"),
    ("攻撃的ミッドフィルダー", "OMF"),
    ("攻撃的ミッドフィールダー", "OMF"),
    ("右ウイング", "RWG"),
    ("右ウィンガー", "RWG"),
    ("左ウイング", "LWG"),
    ("左ウィンガー", "LWG"),
    ("セカンドストライカー", "ST"),
    ("センターフォワード", "CF"),
]


def parse_tm_foot(raw_foot: Optional[str]) -> Optional[str]:
    """TransfermarktやWikipediaの利き足文字列を正規表記（右足 / 左足 / 両足）へ正規化する."""
    if not raw_foot:
        return None
    cleaned = re.sub(r"<[^>]+>|\[[^\]]+\]", "", raw_foot).strip()
    if not cleaned or cleaned in ("-", "?", "不明", "N/A"):
        return None
    if "両" in cleaned or "both" in cleaned.lower():
        if "右" in cleaned:
            return "両足（右足）"
        if "左" in cleaned:
            return "両足（左足）"
        return "両足"
    if "左" in cleaned or "left" in cleaned.lower():
        return "左足"
    if "右" in cleaned or "right" in cleaned.lower():
        return "右足"
    return None


def parse_tm_detailed_position(pos_ja: Optional[str]) -> Tuple[str, str]:
    """Transfermarkt日本語ポジション名を (戦術コード, 日本語ラベル) に変換する."""
    label = (pos_ja or "").strip()
    for key_ja, code in TM_POSITION_MAP:
        if key_ja in label:
            return (code, label)
    if "ディフェンダー" in label or "DF" in label:
        return ("CB", label)
    if "ミッドフ" in label or "MF" in label:
        return ("CMF", label)
    if "フォワード" in label or "ストライカー" in label or "FW" in label:
        return ("CF", label)
    return ("", label)


def parse_tm_height_cm(raw_height: Optional[str]) -> Optional[int]:
    """'1,84m' や '184cm' から整数cmを返す."""
    if not raw_height:
        return None
    text = raw_height.strip().replace(",", ".")
    m_meter = re.search(r"([12]\.\d{2})\s*m", text)
    if m_meter:
        return int(round(float(m_meter.group(1)) * 100))
    m_cm = re.search(r"(1\d{2}|2\d{2})", text)
    if m_cm:
        return int(m_cm.group(1))
    return None


def parse_tm_birthdate(raw_birth: Optional[str]) -> Optional[str]:
    """'1999/06/10 (27)' や '1999年6月10日' を 'YYYY/MM/DD' に正規化する."""
    if not raw_birth:
        return None
    m_slash = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", raw_birth)
    if m_slash:
        y, mo, d = m_slash.groups()
        return f"{int(y):04d}/{int(mo):02d}/{int(d):02d}"
    m_jp = re.search(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日", raw_birth)
    if m_jp:
        y, mo, d = m_jp.groups()
        return f"{int(y):04d}/{int(mo):02d}/{int(d):02d}"
    return None


def parse_tm_market_value_eur(raw_val: Optional[str]) -> Optional[int]:
    """'€1.20M' / '€500K' / '€75k' などの表記をユーロ整数値に変換する."""
    if not raw_val:
        return None
    cleaned = raw_val.strip().replace(",", ".")
    if cleaned in ("-", ""):
        return None
    m_val = re.search(r"€\s*([0-9.]+)\s*([MmKk]|万|億)?", cleaned)
    if not m_val:
        return None
    num = float(m_val.group(1))
    unit = (m_val.group(2) or "").upper()
    if unit == "M":
        return int(round(num * 1_000_000))
    if unit == "K":
        return int(round(num * 1_000))
    return int(round(num))


def _extract_verein_id_from_tag(root: Tag) -> Optional[str]:
    """要素内の /verein/{id} リンクからクラブIDを抽出する."""
    a_tag = root.select_one("a[href*='/verein/']")
    if not a_tag:
        return None
    m = re.search(r"/verein/(\d+)", a_tag.get("href", ""))
    return m.group(1) if m else None


def _extract_inline_player_info(cell: Tag) -> Dict[str, Optional[str]]:
    """選手セル（table.inline-table）から英語名・TM選手ID・詳細ポジション・負傷ツールチップを抽出する."""
    en_name = ""
    tm_player_id = None
    pos_ja = ""
    injury_note = None

    player_a = cell.select_one("a[href*='/profil/spieler/']")
    if player_a:
        en_name = player_a.get_text(" ", strip=True)
        m_pid = re.search(r"/spieler/(\d+)", player_a.get("href", ""))
        if m_pid:
            tm_player_id = m_pid.group(1)

    inline_trs = cell.select("table.inline-table tr")
    if len(inline_trs) >= 2:
        pos_ja = inline_trs[-1].get_text(" ", strip=True)
    elif not en_name:
        en_name = cell.get_text(" ", strip=True)

    for sp in cell.select("span.verletzt-table, span[title]"):
        title = (sp.get("title") or "").strip()
        if title and title != en_name and "キャプテン" not in title:
            injury_note = title
            break

    pos_code, pos_label = parse_tm_detailed_position(pos_ja)
    return {
        "en_name": en_name,
        "tm_player_id": tm_player_id,
        "detailed_position_code": pos_code or None,
        "detailed_position_ja": pos_label or None,
        "injury_note": injury_note,
    }


def _extract_transfer_and_loan_meta(row: Tag, tds: List[Tag]) -> Dict[str, Optional[str]]:
    """行内のツールチップおよび前所属セルから前所属クラブ・ローン元クラブ・ローン期限を抽出する."""
    previous_club: Optional[str] = None
    loan_from_club: Optional[str] = None
    loan_until: Optional[str] = None

    if len(tds) >= 8:
        prev_a = tds[7].select_one("a[title], img[title]")
        if prev_a:
            raw_t = (prev_a.get("title") or "").strip()
            club_part = raw_t.split(": Ablöse")[0].strip()
            if club_part:
                previous_club = club_part

    for el in row.find_all(["a", "span", "img"]):
        title = (el.get("title") or "").strip()
        if not title:
            continue
        m_loan = re.search(r"On loan from\s+(.+?)(?:\s+until\s+([0-9/.-]+))?$", title, re.IGNORECASE)
        if m_loan:
            loan_from_club = m_loan.group(1).strip()
            loan_until = m_loan.group(2).strip() if m_loan.group(2) else None
            break
        m_jp_loan = re.search(r"(.+?)から(?:期限付き|ローン|レンタル)移籍", title)
        if m_jp_loan:
            loan_from_club = m_jp_loan.group(1).strip()
            break

    return {
        "previous_club": previous_club,
        "loan_from_club": loan_from_club,
        "loan_until": loan_until,
    }


def _parse_single_squad_row(row: Tag, team_id: str, col_map: Dict[str, int]) -> Optional[Dict[str, Any]]:
    """スカッド詳細一覧の1行（tr）を辞書にパースする."""
    tds = row.find_all("td", recursive=False)
    if len(tds) < 7:
        return None

    p_info = _extract_inline_player_info(tds[1])
    if not p_info["en_name"]:
        return None

    num_raw = tds[0].get_text(strip=True)
    number = int(num_raw) if num_raw.isdigit() else None

    b_idx = col_map.get("birth", 2)
    nat_idx = col_map.get("nat", 3)
    h_idx = col_map.get("height", 4)
    f_idx = col_map.get("foot", 5)
    join_idx = col_map.get("joined", 6)
    contract_idx = col_map.get("contract")
    mv_idx = col_map.get("mv", len(tds) - 1)

    birthdate = parse_tm_birthdate(tds[b_idx].get_text(" ", strip=True)) if b_idx < len(tds) else None
    nationalities = [
        img.get("title", "").strip()
        for img in (tds[nat_idx].find_all("img") if nat_idx < len(tds) else [])
        if img.get("title")
    ]
    height_cm = parse_tm_height_cm(tds[h_idx].get_text(" ", strip=True)) if h_idx < len(tds) else None
    dominant_foot = parse_tm_foot(tds[f_idx].get_text(" ", strip=True)) if f_idx < len(tds) else None
    joined_date = parse_tm_birthdate(tds[join_idx].get_text(" ", strip=True)) if join_idx < len(tds) else None

    contract_until = None
    if contract_idx is not None and contract_idx < len(tds):
        contract_until = parse_tm_birthdate(tds[contract_idx].get_text(" ", strip=True))

    market_value_eur = (
        parse_tm_market_value_eur(tds[mv_idx].get_text(" ", strip=True))
        if mv_idx < len(tds)
        else None
    )
    transfer_meta = _extract_transfer_and_loan_meta(row, tds)

    return {
        "team_id": team_id,
        "number": number,
        "en_name": p_info["en_name"],
        "tm_player_id": p_info["tm_player_id"],
        "detailed_position_code": p_info["detailed_position_code"],
        "detailed_position_ja": p_info["detailed_position_ja"],
        "birthdate": birthdate,
        "height_cm": height_cm,
        "dominant_foot": dominant_foot,
        "joined_date": joined_date,
        "contract_until": contract_until,
        "market_value_eur": market_value_eur,
        "nationalities": nationalities,
        "previous_club": transfer_meta["previous_club"],
        "loan_from_club": transfer_meta["loan_from_club"],
        "loan_until": transfer_meta["loan_until"],
        "injury_note": p_info["injury_note"],
    }


def _build_squad_col_map(headers: List[str]) -> Dict[str, int]:
    """theadの列名配列から列インデックス辞書を構築する（シーズン表示有無による列ズレ対策）."""
    col_map: Dict[str, int] = {}
    for idx, h in enumerate(headers):
        if "生年月日" in h or "Date of birth" in h:
            col_map["birth"] = idx
        elif "国籍" in h or "Nat." in h:
            col_map["nat"] = idx
        elif "身長" in h or "Height" in h:
            col_map["height"] = idx
        elif "利き足" in h or "Foot" in h:
            col_map["foot"] = idx
        elif "加入日" in h or "Joined" in h:
            col_map["joined"] = idx
        elif "契約" in h or "Contract" in h:
            col_map["contract"] = idx
        elif "市場価値" in h or "Market value" in h:
            col_map["mv"] = idx
    return col_map


def parse_tm_squad_html(html: str, team_id: str) -> List[Dict[str, Any]]:
    """クラブ詳細スカッドHTML（/kader/verein/{id}/plus/1）から全選手リストを抽出する."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.items")
    if not table:
        return []

    headers = [th.get_text(" ", strip=True) for th in table.select("thead th")]
    col_map = _build_squad_col_map(headers)

    results: List[Dict[str, Any]] = []
    for row in table.select("tbody > tr"):
        parsed = _parse_single_squad_row(row, team_id, col_map)
        if parsed:
            results.append(parsed)
    return results


def parse_tm_injuries_html(html: str) -> List[Dict[str, Any]]:
    """J1負傷者一覧HTML（/verletztespieler/wettbewerb/JAP1/plus/1）をパースする."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.items")
    if not table:
        return []

    injuries: List[Dict[str, Any]] = []
    for row in table.select("tbody > tr"):
        tds = row.find_all("td", recursive=False)
        if len(tds) < 7:
            continue
        p_info = _extract_inline_player_info(tds[0])
        if not p_info["en_name"]:
            continue
        vid = _extract_verein_id_from_tag(tds[1]) or _extract_verein_id_from_tag(row)
        team_id = VEREIN_TO_TEAM_ID.get(vid or "", "")
        club_a = tds[1].select_one("a[title], img[title]")
        club_name = (club_a.get("title") or "").strip() if club_a else ""

        injuries.append(
            {
                "team_id": team_id,
                "club_name": club_name,
                "en_name": p_info["en_name"],
                "tm_player_id": p_info["tm_player_id"],
                "detailed_position_code": p_info["detailed_position_code"],
                "injury_type": tds[4].get_text(" ", strip=True),
                "since_date": parse_tm_birthdate(tds[5].get_text(" ", strip=True)),
                "until_date": parse_tm_birthdate(tds[6].get_text(" ", strip=True)),
                "market_value_eur": parse_tm_market_value_eur(tds[7].get_text(" ", strip=True))
                if len(tds) >= 8
                else None,
            },
        )
    return injuries


def parse_tm_suspensions_html(html: str) -> Dict[str, List[Dict[str, Any]]]:
    """J1出場停止・累積リーチ一覧HTML（/sperrenausfaelle/wettbewerb/JAP1/plus/1）をパースする."""
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.select("table.items")
    suspensions: List[Dict[str, Any]] = []
    yellow_reaches: List[Dict[str, Any]] = []

    if len(tables) >= 1:
        for row in tables[0].select("tbody > tr"):
            tds = row.find_all("td", recursive=False)
            if len(tds) < 7:
                continue
            p_info = _extract_inline_player_info(tds[0])
            if not p_info["en_name"]:
                continue
            vid = _extract_verein_id_from_tag(tds[1]) or _extract_verein_id_from_tag(row)
            suspensions.append(
                {
                    "team_id": VEREIN_TO_TEAM_ID.get(vid or "", ""),
                    "en_name": p_info["en_name"],
                    "tm_player_id": p_info["tm_player_id"],
                    "reason": tds[3].get_text(" ", strip=True),
                    "since_date": parse_tm_birthdate(tds[4].get_text(" ", strip=True)),
                    "until_date": parse_tm_birthdate(tds[5].get_text(" ", strip=True)),
                    "matches_count": int(tds[6].get_text(strip=True))
                    if tds[6].get_text(strip=True).isdigit()
                    else 1,
                },
            )

    if len(tables) >= 2:
        for row in tables[1].select("tbody > tr"):
            tds = row.find_all("td", recursive=False)
            if len(tds) < 4:
                continue
            p_info = _extract_inline_player_info(tds[0])
            if not p_info["en_name"]:
                continue
            vid = _extract_verein_id_from_tag(tds[1]) or _extract_verein_id_from_tag(row)
            yc_txt = tds[3].get_text(strip=True)
            yellow_reaches.append(
                {
                    "team_id": VEREIN_TO_TEAM_ID.get(vid or "", ""),
                    "en_name": p_info["en_name"],
                    "tm_player_id": p_info["tm_player_id"],
                    "yellow_cards": int(yc_txt) if yc_txt.isdigit() else 3,
                },
            )

    return {
        "suspensions": suspensions,
        "yellow_reaches": yellow_reaches,
    }


def parse_wiki_wikitext_profile(wikitext: str) -> Dict[str, Any]:
    """日本語版Wikipediaの選手記事Wikitext（Infobox）から利き足・身長・体重・生年月日を抽出する."""
    if not wikitext:
        return {}

    foot: Optional[str] = None
    m_foot = re.search(r"\|\s*利き足\s*=\s*([^\n|}]+)", wikitext)
    if m_foot:
        foot = parse_tm_foot(m_foot.group(1))

    height_cm: Optional[int] = None
    m_height = re.search(r"\|\s*身長\s*=\s*([^\n|}]+)", wikitext)
    if m_height:
        height_cm = parse_tm_height_cm(m_height.group(1))

    weight_kg: Optional[int] = None
    m_weight = re.search(r"\|\s*体重\s*=\s*(\d{2,3})", wikitext)
    if m_weight:
        weight_kg = int(m_weight.group(1))

    return {
        "dominant_foot": foot,
        "height_cm": height_cm,
        "weight_kg": weight_kg,
    }


def fetch_wikipedia_player_profiles(
    player_names: List[str],
    batch_size: int = 45,
    sleep_sec: float = 0.25,
) -> Dict[str, Dict[str, Any]]:
    """日本語版Wikipedia APIで複数選手のInfobox属性（利き足・身長・体重）を一括取得する."""
    title_to_orig: Dict[str, List[str]] = {}
    for orig in player_names:
        if not orig:
            continue
        no_space = re.sub(r"[\s\u3000]+", "", orig)
        mid_dot = re.sub(r"[\s\u3000]+", "・", orig.strip())
        title_to_orig.setdefault(no_space, []).append(orig)
        if mid_dot != no_space:
            title_to_orig.setdefault(mid_dot, []).append(orig)

    all_titles = list(title_to_orig.keys())
    results: Dict[str, Dict[str, Any]] = {}
    headers = {"User-Agent": "FootballRagEnricher/1.0 (JLeague Tactical Analysis)"}

    for start in range(0, len(all_titles), batch_size):
        chunk = all_titles[start : start + batch_size]
        params = {
            "action": "query",
            "redirects": "1",
            "prop": "revisions",
            "rvprop": "content",
            "format": "json",
            "titles": "|".join(chunk),
        }
        try:
            resp = requests.get(WIKI_API_URL, params=params, headers=headers, timeout=15)
            resp.raise_for_status()
            qdata = resp.json().get("query", {})
        except Exception as exc:
            logger.warning("Wikipedia batch query failed at %d: %s", start, exc)
            continue

        redirect_map: Dict[str, str] = {}
        for rd in qdata.get("redirects", []):
            redirect_map[rd["to"]] = rd["from"]
        norm_map: Dict[str, str] = {}
        for nm in qdata.get("normalized", []):
            norm_map[nm["to"]] = nm["from"]

        for page in qdata.get("pages", {}).values():
            revs = page.get("revisions", [])
            if not revs:
                continue
            wikitext = revs[0].get("*", "")
            parsed = parse_wiki_wikitext_profile(wikitext)
            if not any(parsed.values()):
                continue

            final_title = page.get("title", "")
            src_title = redirect_map.get(final_title, final_title)
            src_title = norm_map.get(src_title, src_title)

            matched_origs = title_to_orig.get(src_title) or title_to_orig.get(final_title) or []
            for orig_name in matched_origs:
                existing = results.get(orig_name, {})
                if not existing.get("dominant_foot") and parsed.get("dominant_foot"):
                    results[orig_name] = parsed
                elif orig_name not in results:
                    results[orig_name] = parsed

        if start + batch_size < len(all_titles):
            time.sleep(sleep_sec)

    return results


class TransfermarktJLeagueScraper:
    """Transfermarkt日本語版から全20クラブのスカッド・負傷・出場停止データを取得・キャッシュする."""

    def __init__(self, cache_dir: Path, sleep_sec: float = 0.5) -> None:
        self.cache_dir = cache_dir
        self.sleep_sec = sleep_sec
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        }
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_html(self, url: str) -> str:
        """指定URLからHTML文字列を取得する."""
        resp = requests.get(url, headers=self.headers, timeout=20)
        resp.raise_for_status()
        return resp.text

    def fetch_all_j1_squads(self, force: bool = False) -> Dict[str, List[Dict[str, Any]]]:
        """J1全20クラブの現行詳細スカッド（＋昨季在籍アーカイブ補完）を取得・キャッシュする."""
        cache_path = self.cache_dir / "squads_2026.json"
        if cache_path.exists() and not force:
            return json.loads(cache_path.read_text(encoding="utf-8"))

        all_squads: Dict[str, List[Dict[str, Any]]] = {}
        for idx, club in enumerate(J1_TM_CLUBS_2026, start=1):
            tid = club["team_id"]
            slug = club["tm_slug"]
            vid = club["verein_id"]
            url = f"{TM_BASE_URL}/{slug}/kader/verein/{vid}/plus/1"
            try:
                html = self._get_html(url)
                players = parse_tm_squad_html(html, tid)
                all_squads[tid] = players
                logger.info("[%d/20] TM squad %s (%s): %d players", idx, tid, slug, len(players))
            except Exception as exc:
                logger.warning("Failed TM squad for %s: %s", tid, exc)
                all_squads[tid] = []
            time.sleep(self.sleep_sec)

        cache_path.write_text(
            json.dumps(all_squads, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return all_squads

    def fetch_j1_archive_2025_squads(self, force: bool = False) -> Dict[str, List[Dict[str, Any]]]:
        """2025/26特別大会在籍（現在J2/J3レンタル中・夏退団含む）のスカッド一覧を取得・キャッシュする."""
        cache_path = self.cache_dir / "squads_2025_archive.json"
        if cache_path.exists() and not force:
            return json.loads(cache_path.read_text(encoding="utf-8"))

        archive_squads: Dict[str, List[Dict[str, Any]]] = {}
        for idx, club in enumerate(J1_TM_CLUBS_2026, start=1):
            tid = club["team_id"]
            slug = club["tm_slug"]
            vid = club["verein_id"]
            url = f"{TM_BASE_URL}/{slug}/kader/verein/{vid}/saison_id/2025/plus/1"
            try:
                html = self._get_html(url)
                players = parse_tm_squad_html(html, tid)
                archive_squads[tid] = players
                logger.info("[%d/20] TM 2025 archive %s: %d players", idx, tid, len(players))
            except Exception as exc:
                logger.warning("Failed TM 2025 archive for %s: %s", tid, exc)
                archive_squads[tid] = []
            time.sleep(self.sleep_sec)

        cache_path.write_text(
            json.dumps(archive_squads, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return archive_squads

    def fetch_j1_injuries_and_suspensions(self, force: bool = False) -> Dict[str, Any]:
        """J1全クラブの負傷離脱者リストおよび最新出場停止・警告リーチを取得・キャッシュする."""
        cache_path = self.cache_dir / "injuries_and_suspensions_2026.json"
        if cache_path.exists() and not force:
            return json.loads(cache_path.read_text(encoding="utf-8"))

        inj_url = f"{TM_BASE_URL}/j1-league/verletztespieler/wettbewerb/JAP1/plus/1"
        sus_url = f"{TM_BASE_URL}/j1-league/sperrenausfaelle/wettbewerb/JAP1/plus/1"

        inj_html = self._get_html(inj_url)
        time.sleep(self.sleep_sec)
        sus_html = self._get_html(sus_url)

        payload = {
            "injuries": parse_tm_injuries_html(inj_html),
            "disciplinary": parse_tm_suspensions_html(sus_html),
        }
        cache_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return payload

