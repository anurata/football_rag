# -*- coding: utf-8 -*-
"""
Tests for FC Tokyo Layer 1 & Layer 2 Excel Export.
(tests/test_export_fctokyo_excel.py)
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import openpyxl
import pandas as pd

from scripts.export_fctokyo_layer1_layer2_excel import export_fct_excel


class TestExportFCTokyoExcel(unittest.TestCase):
    """Test suite for FC Tokyo Layer 1/2 Excel exporter."""

    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp())
        self.excel_file = self.temp_dir / "test_fct_dossier.xlsx"

    def tearDown(self) -> None:
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_export_fct_excel_creates_valid_workbook(self) -> None:
        """Verify that the generated Excel contains all required sheets and valid records."""
        out_path = export_fct_excel(output_path=self.excel_file)
        self.assertTrue(out_path.exists(), "Excel file must exist")

        wb = openpyxl.load_workbook(str(out_path))
        expected_sheets = [
            "L2_先進戦術指標",
            "L2_試合戦術プラン推移",
            "L2_クラブ戦術プロファイル",
            "L1_チーム詳細スタッツ75項目",
            "L1_選手別試合出場スタッツ",
            "L1_選手詳細マスター",
            "L1_ゴール・重要イベント",
        ]

        for s_name in expected_sheets:
            self.assertIn(s_name, wb.sheetnames, f"Sheet '{s_name}' must exist in workbook")
            ws = wb[s_name]
            self.assertGreater(ws.max_row, 1, f"Sheet '{s_name}' must contain data rows")

        # 1. Verify CBP values are genuine numbers and not None for both home/away
        df_team = pd.read_excel(str(out_path), sheet_name="L1_チーム詳細スタッツ75項目")
        self.assertFalse(df_team["CBP_パス"].isna().any(), "CBP_パス must not contain NaN")
        self.assertFalse(df_team["CBP_クロス"].isna().any(), "CBP_クロス must not contain NaN")
        self.assertFalse(df_team["CBP_ドリブル"].isna().any(), "CBP_ドリブル must not contain NaN")
        self.assertFalse(df_team["CBP_シュート"].isna().any(), "CBP_シュート must not contain NaN")
        # Ensure CBP_パス is NOT equal to passes_rate (verify no overwrite bug)
        self.assertFalse(
            (df_team["CBP_パス"] == df_team["パス成功率(%)"]).all(),
            "CBP_パス must not be equal to passes_rate (overwrite bug)",
        )

        # 2. Verify strict event_type differentiation
        df_events = pd.read_excel(str(out_path), sheet_name="L1_ゴール・重要イベント")
        event_types = df_events["event_type"].unique()
        self.assertIn("GOAL (得点)", event_types)
        # Goal count should be realistic (not bloated 97 goals)
        goal_count = (df_events["event_type"] == "GOAL (得点)").sum()
        self.assertLess(goal_count, 40, f"Goal count ({goal_count}) must be realistic")

        # 3. Verify Player Master contains detailed specs
        df_master = pd.read_excel(str(out_path), sheet_name="L1_選手詳細マスター")
        self.assertIn("利き足", df_master.columns)
        self.assertIn("身長(cm)", df_master.columns)
        self.assertIn("市場価値(EUR)", df_master.columns)
        self.assertGreater(len(df_master), 30, "Player master must contain all club squad players")


if __name__ == "__main__":
    unittest.main()
