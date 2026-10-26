import os
import re
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


def extract_fctokyo_title(soup: BeautifulSoup, default_title: str = "FC東京 マッチレビュー") -> str:
    """記事タイトル（detail-article__tl または titleタグ）を取得する。"""
    tl_el = soup.find(class_=lambda c: c and "detail-article__tl" in c)
    if tl_el:
        text = tl_el.get_text(strip=True)
        if text:
            return text

    if soup.title:
        title_text = soup.title.get_text(strip=True)
        # 不要なサイト名等の接尾辞を除去
        parts = title_text.split("｜")
        return parts[0].strip() if parts else title_text

    return default_title


def parse_qa_text(text: str) -> dict:
    """'Ｑ、質問文 Ａ、回答文' 形式のテキストを質問と回答の辞書に分解する。"""
    # 全角・半角の Q/A に対応
    pattern = r"^[QＱ]、?\s*(.*?)[AＡ]、?\s*(.*)$"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        question = match.group(1).strip()
        answer = match.group(2).strip()
        return {
            "question": question,
            "answer": answer,
        }
    return {
        "question": "",
        "answer": text.strip(),
    }


def extract_fctokyo_content(soup: BeautifulSoup) -> dict:
    """
    FC TOKYO FANZONE記事本文から、マッチレビュー、監督インタビュー、選手インタビューを抽出する。
    """
    result = {
        "review_intro": [],
        "review_sections": [],
        "coach_name": "松橋力蔵監督",
        "coach_qa": [],
        "player_interviews": {},
    }

    contents = soup.find(class_=lambda c: c and "detail-article__contents" in c)
    if not contents:
        return result

    # 不要なタグ（スクリプト、スタイル、SNSパーツ等）を分解
    for tag in contents(["script", "style", "figure", "img", "iframe"]):
        tag.decompose()

    current_section = "intro"
    current_subsection = ""
    current_player = ""

    for child in contents.children:
        if not child.name:
            continue

        text = child.get_text(strip=True)
        if not text:
            continue

        tag_name = child.name.lower()

        # 大見出し (h1) の判定
        if tag_name == "h1":
            if "マッチレビュー" in text:
                current_section = "review"
            elif "監督" in text and "インタビュー" in text:
                current_section = "coach"
                result["coach_name"] = text.replace("インタビュー", "").strip()
            elif "選手" in text and "インタビュー" in text:
                current_section = "players"
            continue

        # 中見出し (h2) の判定
        if tag_name == "h2":
            if current_section == "review":
                current_subsection = text
                result["review_sections"].append(
                    {
                        "title": current_subsection,
                        "paragraphs": [],
                    },
                )
            elif current_section == "players":
                current_player = text
                if current_player not in result["player_interviews"]:
                    result["player_interviews"][current_player] = []
            continue

        # 本文段落 (p) の処理
        if tag_name == "p":
            if current_section == "intro":
                result["review_intro"].append(text)
            elif current_section == "review":
                if result["review_sections"]:
                    result["review_sections"][-1]["paragraphs"].append(text)
                else:
                    result["review_intro"].append(text)
            elif current_section == "coach":
                qa = parse_qa_text(text)
                result["coach_qa"].append(qa)
            elif current_section == "players":
                if current_player:
                    qa = parse_qa_text(text)
                    result["player_interviews"][current_player].append(qa)

    return result


def format_qa_markdown(qa_list: list[dict]) -> str:
    """Q&AリストをMarkdown形式に整形する。"""
    if not qa_list:
        return "インタビューなし"

    blocks = []
    for item in qa_list:
        q = item.get("question", "")
        a = item.get("answer", "")
        if q:
            blocks.append(f"**Q: {q}**\n\n{a}")
        else:
            blocks.append(a)

    return "\n\n".join(blocks)


def build_fctokyo_markdown(
    match_id: str,
    url: str,
    title: str,
    content_data: dict,
) -> str:
    """抽出データを構造化Markdownテキストに整形する。"""
    lines = [
        f"# {title} (Match ID: {match_id})",
        "",
        "## 【1. 記事概要】",
        f"- **対象URL**: {url}",
        "- **情報ソース**: FC東京オフィシャルホームページ (FC TOKYO FANZONE / TOKYOism)",
        "",
        "## 【2. クラブ公式マッチレビュー】",
    ]

    # レビュー導入（前節振り返り・スタメンなど）
    if content_data["review_intro"]:
        for p in content_data["review_intro"]:
            lines.append(p)
            lines.append("")

    # 各セクション（1st, 2nd など）
    for sec in content_data["review_sections"]:
        lines.append(f"### {sec['title']}")
        lines.append("")
        for p in sec["paragraphs"]:
            lines.append(p)
            lines.append("")

    # 監督インタビュー
    coach_name = content_data.get("coach_name", "松橋力蔵監督インタビュー")
    coach_md = format_qa_markdown(content_data["coach_qa"])
    lines.append(f"## 【3. {coach_name}】")
    lines.append(coach_md)
    lines.append("")

    # 選手インタビュー
    lines.append("## 【4. 選手ロングインタビュー】")
    if content_data["player_interviews"]:
        for player_name, qa_list in content_data["player_interviews"].items():
            lines.append(f"### {player_name}")
            player_md = format_qa_markdown(qa_list)
            lines.append(player_md)
            lines.append("")
    else:
        lines.append("選手インタビューなし\n")

    lines.append("## 【5. 戦術・定性分析メモ（AI / ユーザー追記用）】")
    lines.append("- ここにクラブ公式レビューから得られた戦術的狙いや、監督・選手の意図に関する気づきを記載。")
    lines.append("")

    return "\n".join(lines)


def scrape_fctokyo_match_review(
    match_id: str,
    url: str,
    output_dir: str = "data/markdown",
    headless: bool = True,
) -> str:
    """FC東京公式FANZONE記事からマッチレビュー＆インタビューをスクレイピングし、Markdownを保存する。"""
    print(f"[{match_id}] FC東京公式レビューのスクレイピングを開始します: {url}")

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
            print("  -> ページを読み込み中...")
            # FC東京公式サイトは domcontentloaded で十分取得可能
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)

            soup = BeautifulSoup(page.content(), "html.parser")
            title = extract_fctokyo_title(soup)
            content_data = extract_fctokyo_content(soup)

            sec_count = len(content_data["review_sections"])
            coach_qa_count = len(content_data["coach_qa"])
            player_count = len(content_data["player_interviews"])
            print(
                f"  -> 抽出完了: タイトル: '{title}', レビューセクション ({sec_count}章), 監督Q&A ({coach_qa_count}問), 選手インタビュー ({player_count}名)",
            )

        except Exception as e:
            print(f"スクレイピング中にエラーが発生しました: {e}")
            raise
        finally:
            browser.close()

    markdown_content = build_fctokyo_markdown(
        match_id=match_id,
        url=url,
        title=title,
        content_data=content_data,
    )

    os.makedirs(output_dir, exist_ok=True)
    file_path = os.path.join(output_dir, f"{match_id}_fctokyo.md")

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(markdown_content)

    print(f"成功: FC東京公式レビューを {file_path} に保存しました。\n")
    return file_path


if __name__ == "__main__":
    sample_match_id = "20261025_FCT_MIT"
    sample_url = "https://www.fctokyo.co.jp/fan/fanzone/detail/343147/"
    scrape_fctokyo_match_review(sample_match_id, sample_url)
