# -*- coding: utf-8 -*-
"""
Sync updated mobile viewer HTML and markdown tactical cards to Google Drive and OneDrive.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
EXPORTS_DIR = ROOT_DIR / "exports"

TARGETS = [
    ("Google Drive (Real)", Path(r"K:\マイドライブ\JLeague_RAG")),
    ("OneDrive", Path(os.environ.get("USERPROFILE", "C:/Users/anuratajp")) / "OneDrive" / "サッカー" / "JLeague_RAG"),
]


def sync_all() -> None:
    for name, target_path in TARGETS:
        print(f"Syncing to {name}: {target_path}")
        target_path.mkdir(parents=True, exist_ok=True)

        # 1. Preview markdown
        for md_file in EXPORTS_DIR.glob("*_preview*.md"):
            shutil.copy2(md_file, target_path / md_file.name)
            print(f"  Copied preview: {md_file.name}")

        # 2. Markdown tactical card
        tactical_md = EXPORTS_DIR / "J1_2026_全節戦術カルテ.md"
        if tactical_md.exists():
            shutil.copy2(tactical_md, target_path / "J1_2026_全節戦術カルテ.md")
            print("  Copied J1_2026_全節戦術カルテ.md")

        # 3. Mobile HTML viewer
        mobile_html = EXPORTS_DIR / "mobile_viewer" / "index.html"
        if mobile_html.exists():
            shutil.copy2(mobile_html, target_path / "mobile_viewer.html")
            print("  Copied mobile viewer: mobile_viewer.html")

        # 4. Players Excel directory
        players_src = EXPORTS_DIR / "players"
        if players_src.exists():
            players_dst = target_path / "players"
            players_dst.mkdir(parents=True, exist_ok=True)
            for xlsx_file in players_src.glob("*.xlsx"):
                shutil.copy2(xlsx_file, players_dst / xlsx_file.name)
            print("  Copied players Excel files")

        # 5. NotebookLM directory
        notebook_src = EXPORTS_DIR / "notebooklm"
        if notebook_src.exists():
            notebook_dst = target_path / "notebooklm"
            notebook_dst.mkdir(parents=True, exist_ok=True)
            for doc in notebook_src.glob("*.md"):
                shutil.copy2(doc, notebook_dst / doc.name)
            print("  Copied NotebookLM files")

    print("\n[SUCCESS] Sync completed!")


if __name__ == "__main__":
    sync_all()
