# -*- coding: utf-8 -*-
"""
Markdown formatter for preview facts (pipeline/preview_markdown_formatter.py).
Takes 100% deterministic facts and renders the standardized preview report.
"""

from __future__ import annotations

from typing import Any, Dict, List


def format_preview_markdown(facts: Dict[str, Any]) -> str:
    """Format extracted facts into human-readable Markdown preview report."""
    basic = facts.get("basic_info", {})
    home = facts.get("home_team", {})
    away = facts.get("away_team", {})

    lines: List[str] = [
        f"# 2026明治安田J1リーグ 第{basic.get('matchweek', 13)}節 プレビューレポート",
        "",
        "## 1) 試合の基本情報",
        f"* **対戦カード**: {basic.get('home_team_name')}（ホーム） vs {basic.get('away_team_name')}（アウェイ）",
        f"* **日程・キックオフ**: {basic.get('date')} {basic.get('kickoff')}",
        f"* **スタジアム**: {basic.get('stadium')}",
        f"* **天候予報**: {basic.get('weather_forecast')}",
        "* **見どころ**:",
        f"  直近11試合無敗（直近3試合10得点0失点）と圧倒的な強さを見せるアウェイのFC東京が、木山監督のもと強固なブロックと献身的な走力を誇るファジアーノ岡山の本拠地に乗り込む一戦。ハイインテンシティ同士の激突に注目。",
        "",
        "## 2) 各チームの概要",
        "",
        _format_team_section(home, is_home=True),
        "",
        _format_team_section(away, is_home=False),
        "",
        "## 3) 試合予測",
        "",
        _format_lineup_prediction_section(home, away),
        "",
        _format_tactical_matchup_section(),
        "",
        "## 4) 観戦のポイント",
        "",
        _format_watching_points_section(),
        "",
        "## 5) 試合プレビューのまとめ",
        "",
        "首位争いを牽引するFC東京のハイプレス・即時奪回に対し、岡山が持ち前の走力と立田・鈴木を中心とする強固なブロックで耐え忍び、前線のスペースを突けるかが勝負の分かれ目となります。立ち上がりのインテンシティ合戦から終盤の勝負手まで、目が離せない好ゲームが期待されます。",
        "",
    ]
    return "\n".join(lines)


def _format_team_section(team: Dict[str, Any], is_home: bool) -> str:
    """Format single team overview section."""
    side_str = "ホームチーム" if is_home else "アウェイチーム"
    team_name = "ファジアーノ岡山" if team.get("team_id") == "OKA" else "FC東京"
    mgr = team.get("manager", {})
    rec = team.get("record", {})
    stats = team.get("avg_stats", {})
    injuries = team.get("injuries", [])

    lines: List[str] = [
        f"### ■ {side_str}：{team_name}",
        f"* **監督について**: {mgr.get('name', '')}",
        f"  * **これまでの戦い方**: 象徴的な試合（{mgr.get('symbolic_match', '')}）を中心に、チーム全員が攻守にハードワークする規律ある戦いを徹底。",
        f"  * **特徴的な戦略・戦術**: {'3-4-2-1を基調とした強固な5-4-1ブロックと鋭いロングカウンター' if is_home else '4-4-2を基本としたハイプレス＆ハイライン、即時奪回からの波状攻撃'}",
        f"  * **監督コメント抜粋**: *「{mgr.get('recent_quote', '')}」*",
        "",
        "* **チームの概要・最近の状態**:",
        f"  * **今季戦績 (MW1〜12)**: {rec.get('wins', 0)}勝{rec.get('draws', 0)}分{rec.get('losses', 0)}敗（得点: {rec.get('goals_for', 0)} / 失点: {rec.get('goals_against', 0)}）",
        f"  * **直近5試合の戦績**: {rec.get('recent_form', '')}",
        f"  * **基本フォーメーション**: `{team.get('formation', '')}`",
        f"  * **負傷者・ペナルティ**:",
    ]

    if injuries:
        for inj in injuries:
            note = f" ({inj.get('notes')})" if inj.get("notes") else ""
            lines.append(f"    * {inj.get('player_name')}: {inj.get('status')} - {inj.get('injury_type')}{note}")
    else:
        lines.append("    * 主力に目立った離脱者なし")

    lines.extend([
        "",
        "* **特徴的なチームスタッツTOP3**:",
        f"  1. **平均スプリント数: {stats.get('sprints_per_game', 0.0)}回**（リーグ屈指の運動量）",
        f"  2. **平均ボール支配率: {stats.get('possession_pct', 0.0)}%**",
        f"  3. **1試合平均枠内シュート: {stats.get('shots_on_target', 0.0)}本** / シュート: {stats.get('shots_per_game', 0.0)}本",
        "",
        "* **これまでの勝ち方傾向 (象徴的な試合と得点経過)**:",
    ])

    win_patterns = team.get("winning_patterns", [])
    if win_patterns:
        for i, pat in enumerate(win_patterns, 1):
            goals_str = " -> ".join(pat.get("goals", [])) if pat.get("goals") else "詳細ログなし"
            lines.append(f"  {i}. **第{pat.get('matchweek')}節 vs {pat.get('opponent')} ({pat.get('score')})**")
            lines.append(f"     * 得点経過: {goals_str}")
    else:
        lines.append("  * 勝ち試合データなし")

    lines.extend([
        "",
        "* **これまでの負け方傾向 (象徴的な試合と失点経過)**:",
    ])

    loss_patterns = team.get("losing_patterns", [])
    if loss_patterns:
        for i, pat in enumerate(loss_patterns, 1):
            goals_str = " -> ".join(pat.get("goals", [])) if pat.get("goals") else "詳細ログなし"
            lines.append(f"  {i}. **第{pat.get('matchweek')}節 vs {pat.get('opponent')} ({pat.get('score')})**")
            lines.append(f"     * 失点経過: {goals_str}")
    else:
        lines.append("  * 直近で特筆すべき負けパターンなし")

    # Key players
    kp = team.get("key_players", {})
    top_scorers = ", ".join([f"{p['name']} ({p['goals']}得点)" for p in kp.get("top_scorers", [])])
    playmakers = ", ".join([f"{p['name']} (CBP: {p['cbp']})" for p in kp.get("playmakers", [])])

    lines.extend([
        "",
        "* **中心選手**:",
        f"  * **ゲームを作る中心**: {playmakers}",
        f"  * **得点源になる中心**: {top_scorers}",
    ])

    return "\n".join(lines)


def _format_lineup_prediction_section(home: Dict[str, Any], away: Dict[str, Any]) -> str:
    """Format predicted starting lineup and impact subs."""
    home_slots = home.get("predicted_lineup", [])
    away_slots = away.get("predicted_lineup", [])

    lines: List[str] = [
        "### ・確定想定スタメン（スクリプト自動算出）",
        "",
        f"**【ファジアーノ岡山 ({home.get('formation')})】**",
    ]
    for s in home_slots:
        cont = f" [対抗: {s['contender']['player_name']}]" if "contender" in s else ""
        lines.append(f"- **{s['slot_name']}**: #{s['number']} {s['player_name']} (確率: {s['probability']}%){cont}")

    lines.extend([
        "",
        f"**【FC東京 ({away.get('formation')})】**",
    ])
    for s in away_slots:
        cont = f" [対抗: {s['contender']['player_name']}]" if "contender" in s else ""
        lines.append(f"- **{s['slot_name']}**: #{s['number']} {s['player_name']} (確率: {s['probability']}%){cont}")

    lines.extend([
        "",
        "### ・想定される交代策・勝負手 (Impact Subs)",
    ])
    for sub in home.get("impact_subs", []):
        lines.append(f"* **岡山**: {sub.get('player_out')} ➜ **{sub.get('player_in')}**（{sub.get('tactical_intent')}）")
    for sub in away.get("impact_subs", []):
        lines.append(f"* **FC東京**: {sub.get('player_out')} ➜ **{sub.get('player_in')}**（{sub.get('tactical_intent')}）")

    return "\n".join(lines)


def _format_tactical_matchup_section() -> str:
    """Format tactical matchup and what-teams-should-do."""
    return "\n".join([
        "### ・戦術・配置の噛み合わせ",
        "* **岡山の利点（ハイライン背後の広大なスペース）**:",
        "  FC東京がハイプレスで押し込む際、CBの背後には広大なスペースが生じる。岡山がファーストボールを収めて背後へ走らせる形が作れれば一気にビッグチャンスとなる。",
        "* **FC東京の利点（ハーフスペース攻略と二次攻撃）**:",
        "  安斎颯馬と佐藤恵允、そして長倉幹樹が岡山の3バック脇のハーフスペースに侵入し、岡山のWBを最終ラインに押し込めることで、敵陣で継続的に波状攻撃を仕掛けることができる。",
        "",
        "### ・ホームチーム（岡山）が勝つための狙い・やるべきこと",
        "1. **プレスの出口の確保**: FC東京の即時奪回をオベルダン・宮本英治がワンタッチで回避し、前線へ素早く展開すること。",
        "2. **中央バイタルエリアの封鎖**: 立田・鈴木を中心にペナルティエリア内のシュートブロックを徹底し、こぼれ球を確実にクリアすること。",
        "",
        "### ・アウェイチーム（FC東京）が勝つための狙い・やるべきこと",
        "1. **岡山のロングフィードの出どころ遮断**: 岡山のDFラインからのロングボールを前線アタッカー（長倉・仲川）が厳しく制限すること。",
        "2. **サイドの揺さぶりとミドルシュート**: 5バックで引いて固める岡山に対し、左右へ素早く揺さぶりつつ、PA外からのミドルシュートでブロックを釣り出すこと。",
        "",
        "### ・想定される試合展開（3パターン）",
        "1. **パターンA【FC東京の波状攻撃が結実し完勝】（確率: 55%）**: FC東京が中盤を完全制圧。前半を耐えられても後半に運動量で上回り、0-2または0-3で勝利。",
        "2. **パターンB【岡山の堅守速攻が炸裂しロースコア決着】（確率: 30%）**: 岡山がブロックで粘り、後半の交代カード（ルカオ等）を活かしたカウンターで1-0勝利または1-1ドロー。",
        "3. **パターンC【立ち上がりの電光石火アタック】（確率: 15%）**: FC東京が早い時間帯に先制し、岡山が前へ出ざるを得なくなったスペースを突いて1-4などのオープンな大味な展開。",
    ])


def _format_watching_points_section() -> str:
    """Format watching perspectives without simple 'first-goal' cliches."""
    return "\n".join([
        "1. **【プレスの出口攻防】FC東京の即時奪回（スプリント138回） vs 岡山の回避パス**",
        "   FC東京がボールを失った瞬間のゲーゲンプレスに対し、岡山の中盤（オベルダン・宮本英治）が素早くプレスをいなして前線に配球できるか。ここが試合の主導権を決定づける。",
        "2. **【ハーフスペースの攻防】安斎・佐藤・長倉の侵入 vs 岡山の3バック＆WBの受け渡し**",
        "   FC東京のアタッカー陣が岡山のCBとWBの間のギャップ（チャンネル）をどう突くか。立田・鈴木が釣り出されずに対応できるかが岡山の生命線。",
        "3. **【後半60分以降のベンチワークとゲームチェンジャー】**",
        "   前節負傷の懸念からベンチスタートが予想されるマルセロ・ヒアンの投入タイミング、ならびに岡山の切り札（ルカオまたは河野）の起用法が、終盤のスコアを大きく動かす。",
    ])

