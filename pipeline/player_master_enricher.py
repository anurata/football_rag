"""J1全20クラブ選手マスタ正規化・利き足＆Transfermarkt属性補完パイプライン (pipeline/player_master_enricher.py).

機能:
1. 旧ファイルIDズレ（SAN=広島, KYO=京都 -> HIR=広島, SAN=京都）の冪等マイグレーション
2. 全120試合の出場・ベンチ入り選手のうち未登録選手（夏新加入・途中移籍・2種登録）の自動検出とJ公式/Yahoo補完
3. Transfermarkt日本語版（全20クラブ詳細スカッド）× Wikipedia API × 既存辞書による
   利き足・詳細戦術ポジション・市場価値・ローン元・負傷情報のクロス照合統合
4. config/injury_tracker.json, config/loan_restrictions.json, config/player_dominant_foot.json の非破壊拡充
5. entity_master_players のクリーン同期および player_match_positions 名寄せ100%化
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import requests
from bs4 import BeautifulSoup

from experiments.enrich_entity_master_players import (
    build_player_aliases,
    clean_name_key,
    ensure_schema,
    load_dominant_foot_map,
    make_player_id,
    resolve_dominant_foot,
    safe_int_conversion,
    upsert_player_records,
)
from jleague_player_scraper import J1_CLUBS_2026, parse_player_detail_html
from scrapers.transfermarkt_jleague import (
    TransfermarktJLeagueScraper,
    fetch_wikipedia_player_profiles,
    parse_tm_birthdate,
    parse_tm_foot,
)

logger = logging.getLogger("player_master_enricher")

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_PLAYERS_DIR = ROOT_DIR / "data" / "players"
DEFAULT_YAHOO_DIR = ROOT_DIR / "data" / "raw" / "yahoo"
DEFAULT_TM_CACHE_DIR = ROOT_DIR / "data" / "raw" / "transfermarkt"
DEFAULT_DB_PATH = ROOT_DIR / "data" / "football.db"
DEFAULT_FOOT_JSON = ROOT_DIR / "config" / "player_dominant_foot.json"
DEFAULT_INJURY_JSON = ROOT_DIR / "config" / "injury_tracker.json"
DEFAULT_LOAN_JSON = ROOT_DIR / "config" / "loan_restrictions.json"

CLUB_NAME_BY_ID: Dict[str, str] = {
    c["team_id"]: c["club_name"] for c in J1_CLUBS_2026
}

CLUB_NAME_TO_TEAM_ID: Dict[str, str] = {
    "鹿島アントラーズ": "KAS",
    "水戸ホーリーホック": "MIT",
    "浦和レッズ": "URA",
    "浦和レッドダイヤモンズ": "URA",
    "ジェフユナイテッド千葉": "JEF",
    "柏レイソル": "REY",
    "FC東京": "FCT",
    "ＦＣ東京": "FCT",
    "東京ヴェルディ": "VER",
    "FC町田ゼルビア": "ZEL",
    "ＦＣ町田ゼルビア": "ZEL",
    "川崎フロンターレ": "KAW",
    "横浜F・マリノス": "MAR",
    "横浜Ｆ・マリノス": "MAR",
    "清水エスパルス": "PUL",
    "名古屋グランパス": "NAG",
    "京都サンガF.C.": "SAN",
    "ガンバ大阪": "GAM",
    "セレッソ大阪": "CER",
    "ヴィッセル神戸": "VOB",
    "ファジアーノ岡山": "OKA",
    "サンフレッチェ広島": "HIR",
    "サンフレッチェ広島F.C": "HIR",
    "アビスパ福岡": "FUK",
    "V・ファーレン長崎": "VVN",
    "Ｖ・ファーレン長崎": "VVN",
    "アルビレックス新潟": "NII",
    "サガン鳥栖": "SAG",
    "湘南ベルマーレ": "BEL",
    "北海道コンサドーレ札幌": "CON",
    "ジュビロ磐田": "IWA",
    "横浜FC": "YFC",
}


def _strip_accents(text: str) -> str:
    """ラテン文字のアクセント記号を除去して小文字化する."""
    norm = unicodedata.normalize("NFKD", text or "")
    ascii_only = "".join(ch for ch in norm if not unicodedata.combining(ch))
    return ascii_only.lower()


def tokenize_en_name(en_name: Optional[str]) -> Set[str]:
    """英語選手名を比較用トークン集合へ正規化する."""
    if not en_name:
        return set()
    cleaned = re.sub(r"[^a-z0-9]+", " ", _strip_accents(en_name))
    return {tok for tok in cleaned.split() if len(tok) >= 2}


def normalize_birthdate_str(raw_birth: Optional[str]) -> Optional[str]:
    """'1999/6/10' や '1999-06-10' を '1999/06/10' に揃える."""
    return parse_tm_birthdate(raw_birth)


def normalize_legacy_player_files(players_dir: Path = DEFAULT_PLAYERS_DIR) -> Dict[str, Any]:
    """旧 SAN_players.json(広島) / KYO_players.json(京都) を HIR / SAN に冪等マイグレーションする."""
    san_path = players_dir / "SAN_players.json"
    kyo_path = players_dir / "KYO_players.json"
    hir_path = players_dir / "HIR_players.json"

    migrated = False
    if san_path.exists():
        san_data = json.loads(san_path.read_text(encoding="utf-8"))
        sample_club = san_data[0].get("club_name", "") if san_data else ""
        if "広島" in sample_club:
            for rec in san_data:
                rec["team_id"] = "HIR"
            hir_path.write_text(
                json.dumps(san_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            migrated = True

    if kyo_path.exists():
        kyo_data = json.loads(kyo_path.read_text(encoding="utf-8"))
        for rec in kyo_data:
            rec["team_id"] = "SAN"
        san_path.write_text(
            json.dumps(kyo_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        kyo_path.unlink()
        migrated = True

    return {
        "migrated": migrated,
        "hir_exists": hir_path.exists(),
        "san_exists": san_path.exists(),
        "kyo_exists": kyo_path.exists(),
    }


def _collect_existing_team_keys(players_dir: Path) -> Dict[str, Set[str]]:
    """各クラブJSONに登録済みの氏名クリーンキー集合を返す."""
    result: Dict[str, Set[str]] = {}
    for club in J1_CLUBS_2026:
        tid = club["team_id"]
        fp = players_dir / f"{tid}_players.json"
        keys: Set[str] = set()
        if fp.exists():
            for rec in json.loads(fp.read_text(encoding="utf-8")):
                keys.add(clean_name_key(rec.get("name", "")))
        result[tid] = keys
    return result


def find_missing_match_players(
    players_dir: Path = DEFAULT_PLAYERS_DIR,
    yahoo_dir: Path = DEFAULT_YAHOO_DIR,
    db_path: Path = DEFAULT_DB_PATH,
) -> List[Dict[str, Any]]:
    """全120試合のYahoo /summaryメンバー表を走査し、クラブJSON未登録の選手一覧を抽出する."""
    existing_keys = _collect_existing_team_keys(players_dir)
    gmap_path = yahoo_dir / "game_id_map_2026.json"
    mid_to_gid: Dict[str, str] = {}
    if gmap_path.exists():
        raw_map = json.loads(gmap_path.read_text(encoding="utf-8"))
        mid_to_gid = {v: k for k, v in raw_map.items()}

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT match_id, home_team_id, away_team_id FROM matches WHERE season = 2026 ORDER BY match_id",
        ).fetchall()
    finally:
        conn.close()

    missing_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for match_id, h_id, a_id in rows:
        sum_file = yahoo_dir / f"{match_id}_summary.json"
        if not sum_file.exists():
            continue
        sdata = json.loads(sum_file.read_text(encoding="utf-8"))
        lineup = sdata.get("lineup", {})
        for side_key, tid in (("home", h_id), ("away", a_id)):
            side_obj = lineup.get(side_key, {})
            members = [*side_obj.get("starters", []), *side_obj.get("bench", [])]
            for m in members:
                pname = re.sub(r"[\s\u3000]+", " ", m.get("player_name", "")).strip()
                ckey = clean_name_key(pname)
                if not ckey or ckey in existing_keys.get(tid, set()):
                    continue
                if (tid, ckey) not in missing_map:
                    missing_map[(tid, ckey)] = {
                        "team_id": tid,
                        "player_name": pname,
                        "number": str(m.get("number", "")).strip(),
                        "registered_pos": str(m.get("registered_pos", "")).strip(),
                        "sample_match_id": match_id,
                        "sample_game_id": sdata.get("game_id") or mid_to_gid.get(match_id, ""),
                    }
    return list(missing_map.values())


def _extract_yahoo_player_links_from_summary_html(html: str) -> Dict[str, Tuple[str, str]]:
    """Yahoo /summary HTMLから clean_name -> (jleague_id, yahoo_player_url) 辞書を抽出する."""
    soup = BeautifulSoup(html, "html.parser")
    mapping: Dict[str, Tuple[str, str]] = {}
    for a_tag in soup.select("a[href*='/players/']"):
        href = a_tag.get("href", "")
        m_id = re.search(r"/players/(\d+)", href)
        if not m_id:
            continue
        pname = a_tag.get_text(" ", strip=True)
        ckey = clean_name_key(pname)
        if not ckey:
            continue
        full_url = href if href.startswith("http") else f"https://soccer.yahoo.co.jp{href}"
        mapping[ckey] = (m_id.group(1), full_url)
    return mapping


def _parse_yahoo_player_profile_html(html: str) -> Dict[str, str]:
    """Yahoo選手詳細ページから生年月日・身長・体重・出身地を抽出する."""
    soup = BeautifulSoup(html, "html.parser")
    info: Dict[str, str] = {}
    for th in soup.find_all(["th", "dt"]):
        label = th.get_text(strip=True)
        nxt = th.find_next_sibling(["td", "dd"])
        if not nxt:
            continue
        val = nxt.get_text(" ", strip=True)
        if "生年月日" in label:
            b = parse_tm_birthdate(val)
            if b:
                info["birthdate"] = b
        elif label == "身長":
            m_h = re.search(r"(\d{3})", val)
            if m_h:
                info["height_cm"] = m_h.group(1)
        elif label == "体重":
            m_w = re.search(r"(\d{2,3})", val)
            if m_w:
                info["weight_kg"] = m_w.group(1)
        elif "出身地" in label:
            info["birthplace"] = val
    return info


def build_missing_player_records(
    missing_items: List[Dict[str, Any]],
    sleep_sec: float = 0.25,
) -> List[Dict[str, Any]]:
    """未登録選手リストについてYahoo/J公式からプロフィールを取得し標準選手レコードを構築する."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    summary_link_cache: Dict[str, Dict[str, Tuple[str, str]]] = {}
    built: List[Dict[str, Any]] = []

    for item in missing_items:
        gid = item.get("sample_game_id", "")
        ckey = clean_name_key(item["player_name"])
        jleague_id = ""
        yahoo_url = ""

        if gid:
            if gid not in summary_link_cache:
                try:
                    resp = requests.get(
                        f"https://soccer.yahoo.co.jp/jleague/category/j1/game/{gid}/summary",
                        headers=headers,
                        timeout=15,
                    )
                    resp.raise_for_status()
                    summary_link_cache[gid] = _extract_yahoo_player_links_from_summary_html(resp.text)
                    time.sleep(sleep_sec)
                except Exception as exc:
                    logger.warning("Failed Yahoo summary HTML for %s: %s", gid, exc)
                    summary_link_cache[gid] = {}

            found_pair = summary_link_cache[gid].get(ckey)
            if found_pair:
                jleague_id, yahoo_url = found_pair

        detail: Dict[str, Any] = {
            "player_id": jleague_id or f"M_{item['team_id']}_{item['number']}_{ckey[:6]}",
            "team_id": item["team_id"],
            "name": item["player_name"],
            "name_en": "",
            "club_name": CLUB_NAME_BY_ID.get(item["team_id"], item["team_id"]),
            "position": item["registered_pos"] or "MF",
            "number": item["number"],
            "dominant_foot": "",
            "photo_url": "",
            "thumbnail_url": "",
            "birthplace": "",
            "birthdate": "",
            "height_cm": "",
            "weight_kg": "",
            "matches": "-",
            "goals": "-",
            "jleague_debut": "",
            "jleague_first_goal": "",
            "national_team_caps": "0",
            "strong_points": [],
            "season_stats": {},
            "career_history": [],
        }

        if jleague_id:
            try:
                r_jl = requests.get(
                    f"https://www.jleague.jp/player/{jleague_id}/",
                    headers=headers,
                    timeout=15,
                )
                if r_jl.status_code == 200:
                    jl_parsed = parse_player_detail_html(r_jl.text, jleague_id, {})
                    for fld in (
                        "name_en",
                        "birthplace",
                        "birthdate",
                        "height_cm",
                        "weight_kg",
                        "photo_url",
                        "jleague_debut",
                        "jleague_first_goal",
                        "season_stats",
                        "career_history",
                        "strong_points",
                    ):
                        if jl_parsed.get(fld):
                            detail[fld] = jl_parsed[fld]
                time.sleep(sleep_sec)
            except Exception as exc:
                logger.debug("JLeague detail fallback skipped for %s: %s", jleague_id, exc)

        if yahoo_url and (not detail["height_cm"] or not detail["birthdate"]):
            try:
                r_yh = requests.get(yahoo_url, headers=headers, timeout=15)
                if r_yh.status_code == 200:
                    y_prof = _parse_yahoo_player_profile_html(r_yh.text)
                    for k_fld, v_val in y_prof.items():
                        if v_val and not detail.get(k_fld):
                            detail[k_fld] = v_val
                time.sleep(sleep_sec)
            except Exception as exc:
                logger.debug("Yahoo player fallback skipped for %s: %s", yahoo_url, exc)

        built.append(detail)
    return built


def match_player_with_tm_squad(
    player: Dict[str, Any],
    tm_squad: List[Dict[str, Any]],
    global_tm_by_birth: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> Optional[Dict[str, Any]]:
    """Jリーグ選手辞書とTransfermarkt選手リストを生年月日・英語名トークン・背番号で決定論照合する."""
    p_birth = normalize_birthdate_str(player.get("birthdate"))
    p_tokens = tokenize_en_name(player.get("name_en"))
    p_num = safe_int_conversion(player.get("number"))

    # 1. 同クラブ内で生年月日一致
    if p_birth:
        birth_cands = [tm for tm in tm_squad if tm.get("birthdate") == p_birth]
        if len(birth_cands) == 1:
            return birth_cands[0]
        if len(birth_cands) > 1:
            for cand in birth_cands:
                if p_num is not None and cand.get("number") == p_num:
                    return cand
                if p_tokens and (p_tokens & tokenize_en_name(cand.get("en_name"))):
                    return cand
            return birth_cands[0]

    # 2. 同クラブ内で英語名トークン集合の一致（2トークン以上または単一登録名＋背番号一致）
    if p_tokens:
        for cand in tm_squad:
            c_tokens = tokenize_en_name(cand.get("en_name"))
            if not c_tokens:
                continue
            overlap = p_tokens & c_tokens
            if overlap == p_tokens or overlap == c_tokens or len(overlap) >= 2:
                return cand
            if len(overlap) == 1 and p_num is not None and cand.get("number") == p_num:
                return cand

    # 3. 背番号一致 かつ 生年(YYYY)一致
    if p_num is not None and p_birth:
        p_year = p_birth[:4]
        for cand in tm_squad:
            c_birth = cand.get("birthdate") or ""
            if cand.get("number") == p_num and c_birth[:4] == p_year:
                return cand

    # 4. シーズン途中移籍選手向け: J1他クラブTMスカッドからの生年月日＋英語名/身長照合
    if p_birth and global_tm_by_birth and p_birth in global_tm_by_birth:
        g_cands = global_tm_by_birth[p_birth]
        p_height = safe_int_conversion(player.get("height_cm"))
        for cand in g_cands:
            c_tokens = tokenize_en_name(cand.get("en_name"))
            if p_tokens and (p_tokens & c_tokens):
                return cand
            if p_height and cand.get("height_cm") and abs(p_height - cand["height_cm"]) <= 2:
                return cand

    return None


def apply_tm_attributes_to_player(player: Dict[str, Any], tm_rec: Dict[str, Any]) -> None:
    """照合されたTransfermarkt属性を選手辞書に非破壊で反映する."""
    if tm_rec.get("dominant_foot") and not player.get("dominant_foot"):
        player["dominant_foot"] = tm_rec["dominant_foot"]
    if not player.get("name_en") and tm_rec.get("en_name"):
        player["name_en"] = tm_rec["en_name"]
    if not player.get("birthdate") and tm_rec.get("birthdate"):
        player["birthdate"] = tm_rec["birthdate"]
    if not player.get("height_cm") and tm_rec.get("height_cm"):
        player["height_cm"] = str(tm_rec["height_cm"])

    player["tm_player_id"] = tm_rec.get("tm_player_id")
    player["detailed_position_code"] = tm_rec.get("detailed_position_code")
    player["detailed_position_ja"] = tm_rec.get("detailed_position_ja")
    player["joined_date"] = tm_rec.get("joined_date")
    player["contract_until"] = tm_rec.get("contract_until")
    player["market_value_eur"] = tm_rec.get("market_value_eur")
    player["nationalities"] = tm_rec.get("nationalities", [])
    player["previous_club"] = tm_rec.get("previous_club")
    player["loan_from_club"] = tm_rec.get("loan_from_club")
    player["loan_until"] = tm_rec.get("loan_until")
    if tm_rec.get("injury_note"):
        player["tm_injury_note"] = tm_rec["injury_note"]


def _resolve_club_name_to_id(club_name: Optional[str]) -> Optional[str]:
    """日本語クラブ名から正規 team_id を解決する."""
    if not club_name:
        return None
    cleaned = club_name.strip()
    if cleaned in CLUB_NAME_TO_TEAM_ID:
        return CLUB_NAME_TO_TEAM_ID[cleaned]
    for k, tid in CLUB_NAME_TO_TEAM_ID.items():
        if k in cleaned or cleaned in k:
            return tid
    return None


def sync_injuries_and_loans_configs(
    all_players: List[Dict[str, Any]],
    tm_injuries: List[Dict[str, Any]],
    injury_json_path: Path = DEFAULT_INJURY_JSON,
    loan_json_path: Path = DEFAULT_LOAN_JSON,
) -> Dict[str, int]:
    """Transfermarktの負傷離脱者・期限付き移籍情報を config JSON へ既存エントリ非破壊で統合する."""
    by_tm_id: Dict[str, Dict[str, Any]] = {}
    by_team_tokens: List[Tuple[str, Set[str], Dict[str, Any]]] = []
    for p in all_players:
        if p.get("tm_player_id"):
            by_tm_id[str(p["tm_player_id"])] = p
        toks = tokenize_en_name(p.get("name_en"))
        if toks:
            by_team_tokens.append((p["team_id"], toks, p))

    # 1. Injuries merge
    inj_doc = {"description": "クラブ公式・Transfermarkt負傷離脱およびコンディション追跡マスタ", "injuries": []}
    if injury_json_path.exists():
        inj_doc = json.loads(injury_json_path.read_text(encoding="utf-8"))
    existing_inj = inj_doc.setdefault("injuries", [])
    seen_inj_keys = {(it.get("team_id", ""), clean_name_key(it.get("player_name", ""))) for it in existing_inj}

    added_injuries = 0
    for raw_inj in tm_injuries:
        tid = raw_inj.get("team_id", "")
        if not tid:
            continue
        matched_p = by_tm_id.get(str(raw_inj.get("tm_player_id") or ""))
        if not matched_p:
            i_toks = tokenize_en_name(raw_inj.get("en_name"))
            for cand_tid, cand_toks, cand_p in by_team_tokens:
                if cand_tid == tid and i_toks and (i_toks == cand_toks or len(i_toks & cand_toks) >= 2):
                    matched_p = cand_p
                    break

        pname = matched_p["name"] if matched_p else raw_inj["en_name"]
        ckey = clean_name_key(pname)
        if (tid, ckey) in seen_inj_keys:
            continue

        pid = (
            make_player_id(tid, safe_int_conversion(matched_p.get("number"), 0), pname)
            if matched_p
            else f"TM_{tid}_{raw_inj.get('tm_player_id') or ckey[:8]}"
        )
        since_fmt = (raw_inj.get("since_date") or "").replace("/", "-") or None
        until_fmt = (raw_inj.get("until_date") or "").replace("/", "-") or "復帰時期未定"

        existing_inj.append(
            {
                "player_name": pname,
                "player_id": pid,
                "team_id": tid,
                "injury_type": raw_inj.get("injury_type") or "負傷離脱",
                "diagnosis_date": since_fmt,
                "expected_recovery": until_fmt,
                "status": "OUT",
                "source": "TRANSFERMARKT_JAP1",
                "notes": f"Transfermarkt J1負傷者リスト ({raw_inj.get('detailed_position_code') or ''})".strip(),
            },
        )
        seen_inj_keys.add((tid, ckey))
        added_injuries += 1

    injury_json_path.write_text(
        json.dumps(inj_doc, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 2. Loans merge
    loan_doc = {"description": "Jリーグ期限付き移籍（ローン）選手マスタおよび所属元クラブ公式戦出場制限条項の管理", "loans": []}
    if loan_json_path.exists():
        loan_doc = json.loads(loan_json_path.read_text(encoding="utf-8"))
    existing_loans = loan_doc.setdefault("loans", [])
    seen_loan_keys = {
        (it.get("current_team_id", ""), clean_name_key(it.get("player_name", "")))
        for it in existing_loans
    }

    added_loans = 0
    for p in all_players:
        loan_from = p.get("loan_from_club")
        if not loan_from:
            continue
        tid = p["team_id"]
        pname = p["name"]
        ckey = clean_name_key(pname)
        if (tid, ckey) in seen_loan_keys:
            continue

        parent_id = _resolve_club_name_to_id(loan_from)
        # Jクラブ間ローンは原則として保有元クラブ対戦制限リスクをマーク
        is_domestic_club = parent_id is not None
        existing_loans.append(
            {
                "player_name": pname,
                "player_id": make_player_id(tid, safe_int_conversion(p.get("number"), 0), pname),
                "current_team_id": tid,
                "parent_club_id": parent_id or "OVERSEAS_OR_OTHER",
                "parent_club_name": loan_from,
                "loan_until": p.get("loan_until"),
                "season": 2026,
                "restricted_against_parent": is_domestic_club,
                "source": "TRANSFERMARKT_JAP1",
                "notes": (
                    f"{loan_from}からの期限付き移籍（対戦制限条項の可能性に留意）"
                    if is_domestic_club
                    else f"{loan_from}からの期限付き移籍"
                ),
            },
        )
        seen_loan_keys.add((tid, ckey))
        added_loans += 1

    loan_json_path.write_text(
        json.dumps(loan_doc, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "added_injuries": added_injuries,
        "total_injuries": len(existing_inj),
        "added_loans": added_loans,
        "total_loans": len(existing_loans),
    }


def build_db_player_record_with_tm(
    raw: Dict[str, Any],
    dominant_map: Dict[str, str],
) -> Dict[str, Any]:
    """data/players/*.json の1選手辞書を entity_master_players UPSERT用辞書へ変換する."""
    team_id = raw.get("team_id", "").strip().upper()
    name = re.sub(r"[\s\u3000]+", " ", raw.get("name", "")).strip()
    number = safe_int_conversion(raw.get("number"), 0)
    pos = raw.get("position", "").strip()
    en_name = (raw.get("name_en") or "").strip() or None
    jleague_id = str(raw.get("player_id", "")).strip() or None
    clean_k = clean_name_key(name)
    player_id = make_player_id(team_id, number, name)

    raw_foot = parse_tm_foot(raw.get("dominant_foot")) or raw.get("dominant_foot")
    foot = resolve_dominant_foot(name, raw_foot, dominant_map)
    height = safe_int_conversion(raw.get("height_cm"))
    weight = safe_int_conversion(raw.get("weight_kg"))
    birthdate = (raw.get("birthdate") or "").strip() or None
    photo_url = (raw.get("photo_url") or "").strip() or (raw.get("thumbnail_url") or "").strip() or None

    aliases = build_player_aliases(name, en_name, clean_k)

    profile_details: Dict[str, Any] = {
        "jleague_id": jleague_id,
        "tm_player_id": raw.get("tm_player_id"),
        "club_name": raw.get("club_name"),
        "detailed_position_code": raw.get("detailed_position_code"),
        "detailed_position_ja": raw.get("detailed_position_ja"),
        "birthplace": raw.get("birthplace"),
        "birthdate": birthdate,
        "height_cm": height,
        "weight_kg": weight,
        "dominant_foot": foot,
        "joined_date": raw.get("joined_date"),
        "contract_until": raw.get("contract_until"),
        "market_value_eur": raw.get("market_value_eur"),
        "nationalities": raw.get("nationalities", []),
        "previous_club": raw.get("previous_club"),
        "loan_from_club": raw.get("loan_from_club"),
        "loan_until": raw.get("loan_until"),
        "tm_injury_note": raw.get("tm_injury_note"),
        "matches_total": raw.get("matches"),
        "goals_total": raw.get("goals"),
        "jleague_debut": raw.get("jleague_debut"),
        "jleague_first_goal": raw.get("jleague_first_goal"),
        "national_team_caps": raw.get("national_team_caps"),
        "strong_points": raw.get("strong_points", []),
        "season_stats": raw.get("season_stats", {}),
        "career_history": raw.get("career_history", []),
    }

    return {
        "player_id": player_id,
        "canonical_name": name,
        "team_id": team_id,
        "position": pos,
        "number": number,
        "en_name": en_name,
        "aliases_json": json.dumps(aliases, ensure_ascii=False),
        "jleague_id": jleague_id,
        "birthdate": birthdate,
        "height_cm": height,
        "weight_kg": weight,
        "dominant_foot": foot,
        "photo_url": photo_url,
        "profile_json": json.dumps(profile_details, ensure_ascii=False),
    }


def sync_clean_entity_master_db(
    all_players: List[Dict[str, Any]],
    dominant_map: Dict[str, str],
    db_path: Path = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    """旧誤IDレコード(KYO / 旧広島SAN)を除去し、正規化された全20クラブ選手を entity_master_players へ同期する."""
    parsed_records = [build_db_player_record_with_tm(p, dominant_map) for p in all_players]
    valid_san_ids = {r["player_id"] for r in parsed_records if r["team_id"] == "SAN"}

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = OFF;")
        cur = conn.cursor()
        ensure_schema(cur)

        # 1. Remove invalid KYO team_id records
        cur.execute("DELETE FROM entity_master_players WHERE team_id = 'KYO';")
        deleted_kyo = cur.rowcount

        # 2. Remove stale SAN records that actually belonged to Hiroshima before ID fix
        cur.execute("SELECT player_id FROM entity_master_players WHERE team_id = 'SAN';")
        stale_san_ids = [row[0] for row in cur.fetchall() if row[0] not in valid_san_ids]
        for sid in stale_san_ids:
            cur.execute("DELETE FROM entity_master_players WHERE player_id = ?;", (sid,))

        upserted = upsert_player_records(cur, parsed_records)
        conn.commit()
    finally:
        conn.close()

    return {
        "deleted_kyo": deleted_kyo,
        "deleted_stale_san": len(stale_san_ids),
        "upserted": upserted,
    }


def run_step1_player_master_enrichment(
    players_dir: Path = DEFAULT_PLAYERS_DIR,
    yahoo_dir: Path = DEFAULT_YAHOO_DIR,
    tm_cache_dir: Path = DEFAULT_TM_CACHE_DIR,
    db_path: Path = DEFAULT_DB_PATH,
    foot_json_path: Path = DEFAULT_FOOT_JSON,
    injury_json_path: Path = DEFAULT_INJURY_JSON,
    loan_json_path: Path = DEFAULT_LOAN_JSON,
    force_tm: bool = False,
) -> Dict[str, Any]:
    """Step 1 全体オーケストレーションを実行する."""
    # 1. HIR / SAN ファイル正規化
    mig_stats = normalize_legacy_player_files(players_dir)
    logger.info("Legacy migration: %s", mig_stats)

    # 2. 未登録出場選手の検出とJ公式/Yahoo補完
    missing_items = find_missing_match_players(players_dir, yahoo_dir, db_path)
    logger.info("Found %d missing match players across 120 matches", len(missing_items))
    built_missing = build_missing_player_records(missing_items)
    missing_by_team: Dict[str, List[Dict[str, Any]]] = {}
    for rec in built_missing:
        missing_by_team.setdefault(rec["team_id"], []).append(rec)

    # 3. Transfermarkt 全20クラブ詳細スカッド + 負傷・出場停止取得
    tm_scraper = TransfermarktJLeagueScraper(cache_dir=tm_cache_dir)
    tm_squads = tm_scraper.fetch_all_j1_squads(force=force_tm)
    tm_inj_sus = tm_scraper.fetch_j1_injuries_and_suspensions(force=force_tm)

    global_tm_by_birth: Dict[str, List[Dict[str, Any]]] = {}
    for sq in tm_squads.values():
        for tm_p in sq:
            if tm_p.get("birthdate"):
                global_tm_by_birth.setdefault(tm_p["birthdate"], []).append(tm_p)

    # 4. クラブごとに選手リスト統合 & TM照合
    club_players_map: Dict[str, List[Dict[str, Any]]] = {}
    tm_matched_count = 0
    for club in J1_CLUBS_2026:
        tid = club["team_id"]
        fp = players_dir / f"{tid}_players.json"
        plist: List[Dict[str, Any]] = json.loads(fp.read_text(encoding="utf-8")) if fp.exists() else []
        for p in plist:
            p["team_id"] = tid

        seen_keys = {clean_name_key(p.get("name", "")) for p in plist}
        for m_rec in missing_by_team.get(tid, []):
            mk = clean_name_key(m_rec["name"])
            if mk not in seen_keys:
                plist.append(m_rec)
                seen_keys.add(mk)

        tm_sq = tm_squads.get(tid, [])
        for p in plist:
            matched_tm = match_player_with_tm_squad(p, tm_sq, global_tm_by_birth)
            if matched_tm:
                apply_tm_attributes_to_player(p, matched_tm)
                tm_matched_count += 1

        club_players_map[tid] = plist

    # 5. まだ利き足・体格が空の選手を Wikipedia API + 既存辞書で一括補完
    dominant_map = load_dominant_foot_map(foot_json_path)
    need_wiki_names: List[str] = []
    for plist in club_players_map.values():
        for p in plist:
            existing_f = resolve_dominant_foot(p["name"], p.get("dominant_foot"), dominant_map)
            if existing_f:
                p["dominant_foot"] = existing_f
            if not p.get("dominant_foot") or not p.get("height_cm") or not p.get("weight_kg"):
                need_wiki_names.append(p["name"])

    wiki_profiles = fetch_wikipedia_player_profiles(list(dict.fromkeys(need_wiki_names)))
    wiki_enriched_count = 0
    for plist in club_players_map.values():
        for p in plist:
            w_prof = wiki_profiles.get(p["name"])
            if not w_prof:
                continue
            updated = False
            if not p.get("dominant_foot") and w_prof.get("dominant_foot"):
                p["dominant_foot"] = w_prof["dominant_foot"]
                updated = True
            if not p.get("height_cm") and w_prof.get("height_cm"):
                p["height_cm"] = str(w_prof["height_cm"])
                updated = True
            if not p.get("weight_kg") and w_prof.get("weight_kg"):
                p["weight_kg"] = str(w_prof["weight_kg"])
                updated = True
            if updated:
                wiki_enriched_count += 1

    # 6. 各クラブJSON, all_players.json, player_dominant_foot.json 更新保存
    all_players: List[Dict[str, Any]] = []
    foot_kb_doc = {"description": "J-League Player Dominant Foot Knowledge Base", "version": "2.0.0", "players": {}}
    if foot_json_path.exists():
        foot_kb_doc = json.loads(foot_json_path.read_text(encoding="utf-8"))
    foot_kb_players = foot_kb_doc.setdefault("players", {})

    for club in J1_CLUBS_2026:
        tid = club["team_id"]
        plist = club_players_map[tid]
        out_fp = players_dir / f"{tid}_players.json"
        out_fp.write_text(json.dumps(plist, ensure_ascii=False, indent=2), encoding="utf-8")
        all_players.extend(plist)
        for p in plist:
            if p.get("dominant_foot"):
                foot_kb_players[p["name"]] = p["dominant_foot"]

    (players_dir / "all_players.json").write_text(
        json.dumps(all_players, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    foot_kb_doc["version"] = "2.0.0"
    foot_json_path.write_text(
        json.dumps(foot_kb_doc, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 7. injury_tracker.json & loan_restrictions.json 統合
    cfg_stats = sync_injuries_and_loans_configs(
        all_players=all_players,
        tm_injuries=tm_inj_sus.get("injuries", []),
        injury_json_path=injury_json_path,
        loan_json_path=loan_json_path,
    )

    # 8. entity_master_players 同期
    updated_dom_map = load_dominant_foot_map(foot_json_path)
    db_stats = sync_clean_entity_master_db(all_players, updated_dom_map, db_path=db_path)

    return {
        "migration": mig_stats,
        "missing_added": len(built_missing),
        "total_players": len(all_players),
        "tm_matched": tm_matched_count,
        "wiki_enriched": wiki_enriched_count,
        "configs": cfg_stats,
        "db": db_stats,
    }
