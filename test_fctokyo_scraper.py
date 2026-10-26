import os
import unittest
from bs4 import BeautifulSoup
from fctokyo_scraper import (
    extract_fctokyo_title,
    parse_qa_text,
    extract_fctokyo_content,
    format_qa_markdown,
    build_fctokyo_markdown,
)


class TestFCTokyoScraper(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        html_path = os.path.join(base_dir, "page_fctokyo.html")

        with open(html_path, "r", encoding="utf-8") as f:
            cls.soup = BeautifulSoup(f.read(), "html.parser")

    def test_extract_fctokyo_title(self):
        title = extract_fctokyo_title(self.soup)
        self.assertIn("10/25水戸戦", title)
        self.assertIn("MATCH REVIEW & INTERVIEW", title)

    def test_parse_qa_text(self):
        sample = "Ｑ、本日の試合の総括をお願いします。Ａ、大量得点で、ホームで勝利することができてうれしく思っています。"
        qa = parse_qa_text(sample)
        self.assertEqual(qa["question"], "本日の試合の総括をお願いします。")
        self.assertEqual(qa["answer"], "大量得点で、ホームで勝利することができてうれしく思っています。")

    def test_extract_fctokyo_content(self):
        data = extract_fctokyo_content(self.soup)

        # レビュー導入
        self.assertTrue(len(data["review_intro"]) > 0)
        intro_text = " ".join(data["review_intro"])
        self.assertIn("スターティングイレブン", intro_text)

        # レビューセクション (1st, 2nd)
        self.assertEqual(len(data["review_sections"]), 2)
        sec_titles = [s["title"] for s in data["review_sections"]]
        self.assertTrue(any("1st" in t for t in sec_titles))
        self.assertTrue(any("2nd" in t for t in sec_titles))

        # 監督インタビュー
        self.assertIn("松橋力蔵監督", data["coach_name"])
        self.assertEqual(len(data["coach_qa"]), 6)
        first_coach_qa = data["coach_qa"][0]
        self.assertIn("総括", first_coach_qa["question"])
        self.assertIn("大量得点", first_coach_qa["answer"])

        # 選手インタビュー
        players = list(data["player_interviews"].keys())
        self.assertIn("仲川輝人選手", players)
        self.assertIn("石原広教選手", players)
        self.assertIn("ダニ ゴメス選手", players)
        self.assertIn("常盤亨太選手", players)

        # 仲川選手のQ&A
        nakagawa_qa = data["player_interviews"]["仲川輝人選手"]
        self.assertTrue(len(nakagawa_qa) >= 4)
        self.assertIn("ヘディング", nakagawa_qa[1]["question"])

    def test_build_fctokyo_markdown(self):
        dummy_content = {
            "review_intro": ["前節は引き分けだった。"],
            "review_sections": [
                {
                    "title": "1st―待望の先制点",
                    "paragraphs": ["素晴らしい立ち上がり。"],
                },
            ],
            "coach_name": "松橋力蔵監督",
            "coach_qa": [
                {
                    "question": "試合の総括は？",
                    "answer": "完璧だった。",
                },
            ],
            "player_interviews": {
                "仲川輝人選手": [
                    {
                        "question": "ゴールについて",
                        "answer": "最高です。",
                    },
                ],
            },
        }

        md = build_fctokyo_markdown(
            match_id="TEST_ID",
            url="https://example.com/fctokyo",
            title="10/25 水戸戦 レビュー",
            content_data=dummy_content,
        )

        self.assertIn("# 10/25 水戸戦 レビュー (Match ID: TEST_ID)", md)
        self.assertIn("### 1st―待望の先制点", md)
        self.assertIn("## 【3. 松橋力蔵監督】", md)
        self.assertIn("**Q: 試合の総括は？**", md)
        self.assertIn("### 仲川輝人選手", md)
        self.assertIn("**Q: ゴールについて**", md)


if __name__ == "__main__":
    unittest.main()
