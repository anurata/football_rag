import os
import re
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from pipeline.normalizer import EntityNormalizer


def resolve_canonical_match_id(
    soup: BeautifulSoup,
    url: str,
    normalizer: EntityNormalizer | None = None,
) -> tuple[str | None, str | None]:
    """
    HTML内のTitle、H1、およびURLからJ1の対戦カードと正規match_idを解決する。
    J1の試合でない場合や404・検索ページの場合は (None, None) を返す。
    """
    title_text = soup.title.get_text(strip=True) if soup.title else ""
    h1 = soup.find("h1")
    h1_text = h1.get_text(strip=True) if h1 else ""

    # 404や無効なページの判定
    if h1_text == "404" or "見つかりません" in h1_text:
        return None, None
    if any(k in title_text for k in ["Ｊ２", "Ｊ３", "404"]):
        return None, None

    norm = normalizer or EntityNormalizer()
    home_raw, away_raw = "", ""

    if "vs" in h1_text:
        parts = h1_text.split("vs")
        home_raw, away_raw = parts[0].strip(), parts[1].strip()
    elif "vs" in title_text:
        m = re.search(r"【公式】(.+?)\s*vs\s*(.+?)の試合結果", title_text)
        if m:
            home_raw, away_raw = m.group(1).strip(), m.group(2).strip()

    if not home_raw or not away_raw:
        return None, None

    home_id = norm.normalize_team_name(home_raw)
    away_id = norm.normalize_team_name(away_raw)

    # 両方のチームIDがJ1正規マスターに存在することを確認（J2/J3クラブ混入を防止）
    if not home_id or not away_id:
        return None, None

    # URLから日付（YYYYMMDD）を抽出
    m_url = re.search(r"/(\d{4})/(\d{4})\d{2}/", url)
    if m_url:
        date_str = f"{m_url.group(1)}{m_url.group(2)}"
    else:
        # 日付要素からの抽出フォールバック
        date_el = soup.find(class_=lambda c: c and "o-page-header__date" in c)
        date_text = date_el.get_text(strip=True) if date_el else ""
        m_date = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", date_text)
        if m_date:
            y, m_mon, d = m_date.groups()
            date_str = f"{int(y):04d}{int(m_mon):02d}{int(d):02d}"
        else:
            date_str = "UNKNOWN"

    match_id = f"{date_str}_{home_id}_{away_id}"
    match_title = f"{home_raw} vs {away_raw}"
    return match_id, match_title


def extract_match_title(soup: BeautifulSoup, default_id: str) -> str:
    """試合カード名（h1）を取得する。取得できない場合はデフォルト値を返す。"""
    h1_elem = soup.find("h1")
    if h1_elem:
        title = h1_elem.get_text(strip=True)
        if title and title != "検索":
            return title

    title_elem = soup.find("title")
    if title_elem:
        raw_title = title_elem.get_text(strip=True)
        if raw_title and raw_title != "検索":
            return raw_title

    return f"J1 Match {default_id}"


def extract_basic_info(soup: BeautifulSoup) -> dict:
    """試合日時、スタジアム、天候、観客数、スコア、得点者などの基本情報を抽出する。"""
    info = {
        "date": "",
        "stadium": "",
        "attendance": "",
        "climate": "",
        "home_team": "",
        "away_team": "",
        "score": "",
        "scorers": [],
    }

    # 日時
    date_el = soup.find(class_=lambda c: c and "o-page-header__date" in c)
    if date_el:
        info["date"] = date_el.get_text(strip=True)

    # スタジアム名
    stadium_el = soup.find(class_=lambda c: c and "o-page-header__stadium-name" in c)
    if stadium_el:
        info["stadium"] = stadium_el.get_text(strip=True)

    # 入場者数
    people_el = soup.find(class_=lambda c: c and "o-page-header__stadium-people" in c)
    if people_el:
        info["attendance"] = people_el.get_text(strip=True).replace("入場者数:", "").strip()

    # 気候（天候・気温・湿度）
    climate_el = soup.find(class_=lambda c: c and "o-page-header__stadium-climate" in c)
    if climate_el:
        info["climate"] = climate_el.get_text(strip=True)

    # スコアとチーム名
    score_els = soup.find_all(class_=lambda c: c and "o-page-header__match-score" in c)
    if len(score_els) >= 2:
        home_score = score_els[0].get_text(strip=True)
        away_score = score_els[1].get_text(strip=True)
        info["score"] = f"{home_score} - {away_score}"

    # 得点者一覧
    score_list_el = soup.find(class_=lambda c: c and "o-page-header__player-score-list" in c)
    if score_list_el:
        p_tags = [p for p in score_list_el.find_all("p") if p.get_text(strip=True)]
        scorers = []
        i = 0
        while i < len(p_tags):
            name_text = p_tags[i].get_text(strip=True)
            if i + 1 < len(p_tags):
                time_text = p_tags[i + 1].get_text(strip=True)
                if "'" in time_text or time_text.endswith("分"):
                    scorers.append(f"{name_text} {time_text}")
                    i += 2
                    continue
            scorers.append(name_text)
            i += 1
        info["scorers"] = scorers

    return info


def _format_stat_cell(cell_el) -> str:
    """スタッツセルから値を抽出する。カード枚数がある場合は警告・退場として整形する。"""
    if not cell_el:
        return ""

    cards = cell_el.find_all(
        lambda tag: tag.get("class") and "o-team-comparison__stats-card" in tag.get("class"),
    )
    if cards:
        card_parts = []
        for card in cards:
            badge = card.find(class_=lambda c: c and "a-badge" in c)
            color = badge.get("color", "") if badge else ""
            num_el = card.find(class_=lambda c: c and "stats-card-points" in c)
            num = num_el.get_text(strip=True) if num_el else "0"
            if color == "yellow":
                card_parts.append(f"警告:{num}")
            elif color == "red":
                card_parts.append(f"退場:{num}")
            else:
                card_parts.append(num)
        return " / ".join(card_parts)

    return cell_el.get_text(strip=True)


def extract_team_stats(soup: BeautifulSoup) -> list[dict]:
    """両チームのスタッツ比較データ（シュート数、支配率等）を抽出する。"""
    stats_list = []
    comp = soup.find(class_=lambda c: c and "o-team-comparison--game-average-matchup" in c)
    if not comp:
        return stats_list

    title_col = comp.find(class_=lambda c: c and "o-team-comparison__stats-title-col" in c)
    if not title_col:
        return stats_list

    titles = [
        t.get_text(strip=True)
        for t in title_col.find_all(class_=lambda c: c and "o-team-comparison__stats-title" in c)
    ]

    home_items = comp.find_all(class_=lambda c: c and "o-team-comparison__stats-info--home" in c)
    away_items = comp.find_all(class_=lambda c: c and "o-team-comparison__stats-info--away" in c)

    for i, title in enumerate(titles):
        home_val = _format_stat_cell(home_items[i]) if i < len(home_items) else ""
        away_val = _format_stat_cell(away_items[i]) if i < len(away_items) else ""
        stats_list.append(
            {
                "label": title,
                "home": home_val,
                "away": away_val,
            },
        )

    return stats_list


def extract_match_report(soup: BeautifulSoup) -> str:
    """戦評タブ内の公式マッチレポート（本文段落）を抽出する。"""
    editorial = soup.find(class_=lambda c: c and "p-game-details-highlight__review-editorial" in c)
    if not editorial:
        editorial = soup.find(class_=lambda c: c and "review-editorial" in c)
    if not editorial:
        return "マッチレポートが見つかりませんでした。"

    # button等の不要なUI要素を除去
    for b in editorial.find_all(["button", "svg", "span.a-typography--visually-hidden"]):
        b.decompose()

    paragraphs = []
    for p in editorial.find_all("p"):
        text = p.get_text(strip=True)
        if text and len(text) > 10 and not text.startswith("続きを読む"):
            paragraphs.append(text)

    if paragraphs:
        return "\n\n".join(paragraphs)

    # pタグで見つからなかった場合のフォールバック
    full_text = editorial.get_text("\n", strip=True)
    lines = [
        line.strip()
        for line in full_text.splitlines()
        if len(line.strip()) > 15 and "続きを読む" not in line
    ]
    return "\n\n".join(lines) if lines else "マッチレポートの抽出に失敗しました。"


def extract_comments(soup: BeautifulSoup, section_keyword: str) -> list[dict]:
    """
    指定されたセクション（'選手コメント' または '監督コメント'）に属するコメント一覧を抽出する。
    戻り値: [{'club': str, 'name': str, 'content': str}]
    """
    comments = []
    all_comment_nodes = soup.find_all(class_=lambda c: c and "player-comment" == c.strip())

    for c in all_comment_nodes:
        # このコメントがどのセクションに属しているか（直前の見出しを確認）
        matched_section = False
        curr = c
        while curr:
            prev_header = curr.find_previous(["h1", "h2", "h3"])
            if prev_header:
                header_text = prev_header.get_text(strip=True)
                if section_keyword in header_text:
                    matched_section = True
                    break
                elif any(k in header_text for k in ["選手コメント", "監督コメント"]):
                    # 別のコメントセクションの見出しにヒットした場合は対象外
                    break
            curr = curr.parent

        if not matched_section:
            continue

        # 氏名
        name_el = c.find(class_=lambda x: x and "player-comment__name" in x)
        name = name_el.get_text(strip=True) if name_el else "不明"

        # 所属クラブ
        club_name = ""
        club_el = c.find_parent(class_=lambda x: x and "p-game-details-highlight__comment-list" in x)
        if club_el:
            club_header = club_el.find(class_=lambda x: x and "p-game-details-highlight__comment-club" in x)
            if club_header:
                club_name = club_header.get_text(strip=True)

        # 本文
        content_el = c.find(class_=lambda x: x and "player-comment__content" in x)
        content = ""
        if content_el:
            for b in content_el.find_all(["button", "svg"]):
                b.decompose()
            raw_lines = [
                line.strip()
                for line in content_el.get_text("\n", strip=True).splitlines()
                if line.strip() and "続きを読む" not in line
            ]
            content = "\n".join(raw_lines)

        if content:
            comments.append(
                {
                    "club": club_name,
                    "name": name,
                    "content": content,
                },
            )

    return comments


def format_comments_markdown(comments: list[dict], default_empty_message: str) -> str:
    """コメントリストをMarkdown形式に整形する。"""
    if not comments:
        return default_empty_message

    blocks = []
    for c in comments:
        club_prefix = f"【{c['club']}】" if c["club"] else ""
        header = f"#### {club_prefix}{c['name']}"
        body = c["content"]
        blocks.append(f"{header}\n{body}")

    return "\n\n".join(blocks)


def format_stats_markdown(stats: list[dict]) -> str:
    """スタッツリストをMarkdownテーブルに整形する。"""
    if not stats:
        return "スタッツデータなし"

    lines = [
        "| 指標 | HOME | AWAY |",
        "| :--- | :---: | :---: |",
    ]
    for s in stats:
        lines.append(f"| {s['label']} | {s['home']} | {s['away']} |")

    return "\n".join(lines)


def build_markdown_content(
    match_id: str,
    base_url: str,
    title: str,
    basic_info: dict,
    stats: list[dict],
    report_text: str,
    coach_comments: list[dict],
    player_comments: list[dict],
    matchweek: int | None = None,
) -> str:
    """各セクションを統合して構造化Markdownを生成する。"""
    stats_md = format_stats_markdown(stats)
    coach_md = format_comments_markdown(coach_comments, "監督コメントなし")
    player_md = format_comments_markdown(player_comments, "選手コメントなし")

    scorers_text = "、".join(basic_info.get("scorers", [])) if basic_info.get("scorers") else "なし"
    score_display = basic_info.get("score", "試合終了")
    mw_line = f"- **節数**: 第{matchweek}節\n" if matchweek is not None else ""

    markdown = f"""# {title} (Match ID: {match_id})

## 【1. 試合概要・基本データ】
- **対象URL**: {base_url}
{mw_line}- **開催日時**: {basic_info.get('date', '不明')}
- **スタジアム**: {basic_info.get('stadium', '不明')}
- **入場者数**: {basic_info.get('attendance', '不明')}
- **天候・気候**: {basic_info.get('climate', '不明')}
- **試合結果**: {score_display}
- **得点経過**: {scorers_text}

### 【チームスタッツ比較】
{stats_md}

## 【2. 公式マッチレポート】
{report_text}

## 【3. 監督・選手コメント（定性の核）】
### 【監督コメント】
{coach_md}

### 【選手コメント】
{player_md}

## 【4. 分析・観察メモ（AI / ユーザー追記用）】
- ここに試合を通じた戦術的気づきや、次節に向けた課題を記載。
"""
    return markdown


def scrape_jleague_match_page(
    page,
    match_id: str,
    base_url: str,
    output_dir: str = "data/markdown",
    matchweek: int | None = None,
    normalizer: EntityNormalizer | None = None,
) -> str | None:
    """既存のPlaywright Pageオブジェクトを用いてデータを抽出し、Markdownを保存する。
    J1の有効な試合でない場合はNoneを返し、保存をスキップする。
    """
    print(f"[{match_id}] クレンジング強化型スクレイピングを開始します: {base_url}")

    # 1. サマリー画面の取得
    print("  -> サマリー画面を読み込み中...")
    try:
        page.goto(base_url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(1000)
    except Exception as e:
        print(f"  [スキップ] ページ遷移エラー: {e}")
        return None

    summary_soup = BeautifulSoup(page.content(), "html.parser")

    # 自己整合性検証: ページの真のmatch_idと対戦カード名を解決
    canonical_id, canonical_title = resolve_canonical_match_id(
        soup=summary_soup,
        url=base_url,
        normalizer=normalizer,
    )

    if canonical_id is None:
        print(f"  [スキップ] J1の有効な試合ページではないためスキップします: {base_url}")
        return None

    # 呼び出し元match_idと不一致がある場合は真のIDを採用
    if canonical_id != match_id:
        print(f"  [自動補正] match_idを正規化補正しました: {match_id} -> {canonical_id}")
        match_id = canonical_id

    match_title = canonical_title or extract_match_title(summary_soup, match_id)
    basic_info = extract_basic_info(summary_soup)
    stats = extract_team_stats(summary_soup)

    # 2. 戦評タブの表示・取得
    print("  -> 戦評タブに切り替え中...")
    review_link = page.query_selector("a[href*='#review']")
    if review_link:
        try:
            review_link.click()
            page.wait_for_timeout(1500)
        except Exception:
            review_url = base_url.rstrip("/") + "/#review"
            page.goto(review_url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(1000)
    else:
        review_url = base_url.rstrip("/") + "/#review"
        try:
            page.goto(review_url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(1000)
        except Exception:
            pass

    review_soup = BeautifulSoup(page.content(), "html.parser")

    report_text = extract_match_report(review_soup)
    coach_comments = extract_comments(review_soup, "監督コメント")
    player_comments = extract_comments(review_soup, "選手コメント")

    print(
        f"  -> 抽出完了: 戦評 ({len(report_text)}文字), 監督コメント ({len(coach_comments)}件), 選手コメント ({len(player_comments)}件)",
    )

    # 3. 構造化Markdownの保存
    markdown_content = build_markdown_content(
        match_id=match_id,
        base_url=base_url,
        title=match_title,
        basic_info=basic_info,
        stats=stats,
        report_text=report_text,
        coach_comments=coach_comments,
        player_comments=player_comments,
        matchweek=matchweek,
    )

    os.makedirs(output_dir, exist_ok=True)
    file_path = os.path.join(output_dir, f"{match_id}.md")

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(markdown_content)

    print(f"成功: クレンジング済みのデータを {file_path} に保存しました。\n")
    return file_path


def scrape_jleague_match(
    match_id: str,
    base_url: str,
    output_dir: str = "data/markdown",
    matchweek: int | None = None,
    headless: bool = True,
) -> str:
    """Playwrightを用いてJリーグ公式試合ページからデータをスクレイピングし、構造化Markdownを保存する。"""
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
        try:
            return scrape_jleague_match_page(
                page=page,
                match_id=match_id,
                base_url=base_url,
                output_dir=output_dir,
                matchweek=matchweek,
            )
        finally:
            browser.close()


if __name__ == "__main__":
    sample_match_id = "20261025_FCT_MIT"
    sample_url = "https://www.jleague.jp/match/j1/2026/102505/"
    scrape_jleague_match(sample_match_id, sample_url)