"""
Tactical Analyst Prompts for J-League RAG system.
Covers the '9 Core Tactical Questions' and '4 Watching Perspectives/Lenses'.
"""

from typing import Dict, Any, List, Optional
import json

SYSTEM_PROMPT = """あなたはJリーグのトッププロ戦術分析官（データアナリスト兼ヘッドコーチアドバイザー）です。
単なるスタッツの羅列や結果論・精神論を一切排し、以下の原則に基づいた極めて精度の高い因果推論と戦術評価を行ってください。

【分析原則】
1. **ファクト至上主義**: 主張や仮説には、必ず提示された客観データ（xG、走行距離、スプリント、パス成功率、座標、得失点推移）を根拠として結びつけてください。
2. **因果ツリーと消去法 (Why)**: 単一の理由を決めつけず、フィジカル・戦術構造・相手の対策などの複数仮説を立て、データと照合して反証・消去法で真因を絞り込んでください。
3. **二面性のトレードオフ (What-if / How)**: 戦術の変更や改善策を提示する際は、狙い（光：主作用）と必ずセットで相手に逆手に取られる構造的リスク（影：副作用）を提示してください。
4. **観戦者への翻訳（4つのレンズ）**: 専門的知見を、ピッチや画面の「ボールのない場所」「特定時間帯」のどこを見れば一般ファンでも一目で体感できるかの観戦ガイドへ昇華させてください。
"""

WATCHING_LENSES_GUIDE = """
以下の「観戦が10倍面白くなる4つのレンズ」のフォーマットに沿って構造化して出力してください：

1. 【開始10分の「配置の答え合わせ」】
   - ボールがないところで誰が誰をマークし、どこにスペースが空いているか。
2. 【守備のスイッチが入る「トリガー」の瞬間】
   - 相手の誰にどんなパス・トラップが入った瞬間に一斉にプレスへ連動するか。
3. 【試合の流れを知らせる「炭鉱のカナリア（先行指標）」】
   - スコアが動く前に、セカンドボール回収位置やラインの高さで優劣を見極めるポイント。
4. 【後半60分の「ベンチのチェス（交代カードの意図）」】
   - 投入された選手のロールから読み解く、追加点狙いか逃げ切りかのベンチの意図とリスク。
"""


def format_fact_chunks_text(fact_chunks: List[Dict[str, Any]]) -> str:
    """Format Layer 1 retrieved chunks into markdown text."""
    if not fact_chunks:
        return "（該当する試合ファクトチャンクなし）\n"

    lines = []
    for i, c in enumerate(fact_chunks, 1):
        meta = c.get("metadata", {})
        ctype = meta.get("chunk_type", "chunk")
        mid = meta.get("match_id", "")
        lines.append(f"### [ファクト {i}] 試合ID: {mid} / 種別: {ctype}")
        lines.append(c.get("content", "").strip())
        lines.append("")
    return "\n".join(lines)


def format_causal_hypotheses_text(trees: List[Dict[str, Any]]) -> str:
    """Format Layer 2 metric causal trees into markdown text."""
    if not trees:
        return "（該当する因果仮説ツリーなし）\n"

    lines = []
    for tree in trees:
        m_name = tree.get("metric_name", "")
        lines.append(f"#### ■ 指標: {m_name}")
        lines.append(f"現象: {tree.get('phenomenon', '')}")
        for h in tree.get("hypotheses", []):
            lines.append(f"- **仮説 {h.get('hypothesis_id')}: {h.get('name')}**")
            lines.append(f"  - 内容: {h.get('description')}")
            v_metrics = [
                f"{v.get('metric')} ({v.get('expected_pattern')})"
                for v in h.get("verification_metrics", [])
            ]
            if v_metrics:
                lines.append(f"  - 検証指標: {'; '.join(v_metrics)}")
            if h.get("elimination_condition"):
                lines.append(f"  - 消去条件: {h.get('elimination_condition')}")
        lines.append("")
    return "\n".join(lines)


def format_tradeoffs_text(tradeoffs: List[Dict[str, Any]]) -> str:
    """Format Layer 2 tactical tradeoffs into markdown text."""
    if not tradeoffs:
        return "（該当する戦術トレードオフ辞書なし）\n"

    lines = []
    for t in tradeoffs:
        t_name = t.get("tactic_name", "")
        lines.append(f"#### ■ 戦術: {t_name} ({t.get('category', '')})")
        lines.append(f"メカニズム: {t.get('core_mechanism', '')}")

        lines.append("- **主作用（メリット・狙い）**:")
        for me in t.get("main_effects", []):
            lines.append(f"  - {me.get('summary')}: {me.get('description')}")

        lines.append("- **副作用（構造的リスク）**:")
        for se in t.get("side_effects", []):
            lines.append(f"  - [{se.get('severity', 'MID')}] {se.get('risk_name')}: {se.get('description')}")

        vulns = t.get("vulnerability_conditions", [])
        if vulns:
            lines.append(f"- 脆弱化する条件: {'; '.join(vulns)}")
        lines.append("")
    return "\n".join(lines)


def format_system_matchup_text(matchup: Optional[Dict[str, Any]]) -> str:
    """Format Layer 2 formation matchup dynamics into markdown text."""
    if not matchup:
        return "（該当するシステム噛み合わせ情報なし）\n"

    lines = [
        f"#### ■ システム噛み合わせ: {matchup.get('name', '')}",
        "- **自チーム側の構造的優位性**:",
    ]
    for adv in matchup.get("advantages_for_a", []):
        lines.append(f"  - {adv.get('zone')}: {adv.get('description')}")

    lines.append("- **相手チーム側の構造的優位性**:")
    for adv in matchup.get("advantages_for_b", []):
        lines.append(f"  - {adv.get('zone')}: {adv.get('description')}")

    lines.append("- **ピン留めの力学**:")
    for pin in matchup.get("pinning_mechanisms", []):
        lines.append(f"  - {pin}")

    lines.append("- **ハーフスペースの力学**:")
    for hs in matchup.get("half_space_dynamics", []):
        lines.append(f"  - {hs}")

    lines.append("- **観戦視点のヒント**:")
    for wp in matchup.get("watching_perspective_guide", []):
        lines.append(f"  - {wp}")

    return "\n".join(lines)


# -------------------------------------------------------------
# 9つの問い プロンプトビルダー群
# -------------------------------------------------------------

def build_why_prompt(
    phenomenon: str,
    match_facts: str,
    quantitative_summary: str,
    causal_hypotheses: str,
) -> str:
    """1. 【要因分析 (Why)】プロンプト構築"""
    return f"""以下の現象に対し、提示された定量データと因果仮説ツリーをもとに、消去法で真因を特定してください。

【分析対象の現象】
{phenomenon}

【客観的定量スタッツ】
{quantitative_summary}

【試合ファクト・レポート】
{match_facts}

【因果仮説ツリー（消去法検証用）】
{causal_hypotheses}

【出力要件】
1. 提示された各仮説（H1, H2, H3...）に対して、データとの整合性を1つずつ検証。
2. データと矛盾する仮説を「消去理由」とともに明確に棄却（消去法）。
3. 最終的に残った真因（単独または複合）を特定し、戦術的メカニズムを解説。
"""


def build_how_prompt(
    bottleneck: str,
    quantitative_summary: str,
    tradeoffs_knowledge: str,
    system_matchup: str,
) -> str:
    """2. 【改善処方箋 (How)】プロンプト構築"""
    return f"""以下の課題・ボトルネックを改善するための処方箋を提示してください。

【課題・ボトルネック】
{bottleneck}

【定量スタッツ】
{quantitative_summary}

【戦術トレードオフ辞書】
{tradeoffs_knowledge}

【システム噛み合わせ】
{system_matchup}

【出力要件】
1. **構造的解決策**: ポジショニング、ピン留め、レーン移動など戦術配置による解決。
2. **属人的解決策**: 選手のロール変更、特定の選手交代（リフレッシュや役割変更）による解決。
3. **副作用と対策**: 改善策を採用した場合に生じるリスク（相手のカウンター等）とその防衛策。
"""


def build_what_if_prompt(
    tactical_change: str,
    opponent_stats: str,
    tradeoffs_knowledge: str,
    system_matchup: str,
) -> str:
    """3. 【反実仮想予測 (What-if)】プロンプト構築"""
    return f"""以下の戦術変更を実施した場合のシミュレーションを行ってください。

【提案された戦術変更】
{tactical_change}

【対戦相手の強み・スタッツ】
{opponent_stats}

【戦術トレードオフ辞書】
{tradeoffs_knowledge}

【システム噛み合わせ】
{system_matchup}

【出力要件】
1. **メインシナリオ（光）**: 狙い通り機能した場合に得られる数的優位・決定機創出のメカニズム。
2. **リスクシナリオ（影）**: 相手の強みと衝突し、逆手に取られて失点・被弾する具体的ルート。
3. **成否の分岐点**: 試合開始何分、あるいはどのエリアで何が起きたら変更を撤回・修正すべきかのトリガー。
"""


def build_word_and_deed_prompt(
    coach_claims: str,
    actual_stats: str,
    match_facts: str,
) -> str:
    """4. 【言行一致の検証】プロンプト構築"""
    return f"""監督の試合後コメントや主張が、客観データおよび試合展開と一致しているか検証してください。

【監督の発言・主張】
{coach_claims}

【客観的定量データ・前後半スタッツ】
{actual_stats}

【試合展開・ファクト】
{match_facts}

【出力要件】
1. **主張とデータの対比検証**: 監督の「狙い通り」「修正できた」等の各発言に対し、該当スタッツ（xG、時間帯被シュート、走行距離等）で検証。
2. **判定**: 「実態通りの納得の修正」「結果オーライの勝利（内容は劣勢）」「データは改善していた不運な敗戦」のいずれかに分類して結論を述べてください。
"""


def build_unsung_hero_prompt(
    player_impact: Dict[str, Any],
    player_stats: str,
) -> str:
    """5. 【黒子（陰のMVP）の発掘】プロンプト構築"""
    return f"""ゴールやアシスト等の派手なスタッツに表れにくい「陰のMVP（黒子）」としての貢献度を分析してください。

【選手のOn/Off影響度データ】
{json.dumps(player_impact, ensure_ascii=False, indent=2)}

【個人スタッツ・平均ポジション】
{player_stats}

【出力要件】
1. 該当選手が出場している時間帯（On）と不在時（Off）のチームxG、平均勝点、失点率の差異を評価。
2. 平均ポジション座標や走行量から、ピッチ上でどのような「スペース管理」「カバーリング」「ボールの中継」を行っているか推論。
3. この選手がチーム戦術に与えている不可欠な影響を言語化。
"""


def build_chemistry_prompt(
    pairing_data: Dict[str, Any],
) -> str:
    """6. 【相性・ケミストリー分析】プロンプト構築"""
    return f"""2名の選手の縦・横のユニットとしての相性と相乗効果を分析してください。

【ペア同時出場データ】
{json.dumps(pairing_data, ensure_ascii=False, indent=2)}

【出力要件】
1. 2名の平均距離感（avg_distance）とピッチ上での役割分担（例：1枚が釣り出してもう1枚が裏へ侵入、等）。
2. 同時出場時のチーム得点力・xGの傾向。
3. 2人が並び立つことで最大化される戦術的強み。
"""


def build_game_state_dna_prompt(
    game_state_data: List[Dict[str, Any]],
) -> str:
    """7. 【スコア状況別の体質診断】プロンプト構築"""
    return f"""スコア状況別（先制時・同点時・ビハインド時）のチーム体質（DNA）を診断してください。

【スコア状況別スタッツ】
{json.dumps(game_state_data, ensure_ascii=False, indent=2)}

【出力要件】
1. 先制直後（LEADING）に、ラインが下がって受け身になる体質か、畳み掛けて追加点を奪いに行く体質かの診断。
2. ビハインド時（TRAILING）の攻撃効率と守備バランスの崩壊リスク。
3. この体質に対する戦術的処方箋。
"""


def build_tactical_evolution_prompt(
    team_id: str,
    trajectory_summary: str,
    opponent_interviews: str,
    tradeoffs_knowledge: Optional[str] = None,
) -> str:
    """8. 【戦術の賞味期限と進化】プロンプト構築"""
    tradeoffs_section = (
        f"\n【戦術トレードオフ辞書】\n{tradeoffs_knowledge}\n"
        if tradeoffs_knowledge
        else ""
    )
    return f"""チーム（{team_id}）の戦術が相手に対策・研究された推移と、それに対するチームの進化・マイナーチェンジを分析してください。

【時系列スタッツ推移】
{trajectory_summary}

【対戦相手側の証言・監督コメント（対策の痕跡）】
{opponent_interviews}
{tradeoffs_section}
【出力要件】
1. **相手による対策・研究の分析**: 相手チームがどのエリアを消し、誰をピン留め・封鎖してきたか（証言とスタッツから特定）。
2. **チーム側のマイナーチェンジ**: 対策に対し、監督やチームが施した微修正（ビルドアップ形状、選手のポジショニング、交代策の工夫）。
3. **賞味期限と次の進化課題**: 現在の戦術が今後も通用するか、更なる対策を破るための次の進化軸を提示。
"""


def build_skill_vs_luck_prompt(
    team_id: str,
    trajectory_summary: str,
) -> str:
    """9. 【実力と運の切り分け】プロンプト構築"""
    return f"""チーム（{team_id}）の現在の成績が「実力通り」か、それとも「実得点とxGの乖離（運・偶発性の偏り）」によるものかを診断してください。

【直近試合の得失点 vs xG・被xG推移】
{trajectory_summary}

【出力要件】
1. **攻撃の運・実力診断**: 実得点とxGの乖離度（xg_goal_diff）を評価。チャンス構築の質（実力）か、決定力の一時的フィーバー/決定力不足（運）かを切り分け。
2. **守備の運・実力診断**: 失点数と被xGの乖離度を評価。組織的な被シュート抑制（実力）か、GKのスーパーセーブ連発/被弾の偏り（運）かを切り分け。
3. **揺り戻し（回帰傾向）予測と提言**: 今後期待される成績の収斂方向と、勝点を安定維持するために改善すべき本質的スタッツ指標を提示。
"""


def build_watching_guide_prompt(
    match_facts: str,
    system_matchup: str,
    quantitative_summary: str,
    player_roles_info: Optional[str] = None,
    substitutions_info: Optional[str] = None,
) -> str:
    """観戦が10倍面白くなる4つのレンズ プロンプト構築"""
    roles_section = (
        f"\n【注目選手と戦術ロール】\n{player_roles_info}\n"
        if player_roles_info
        else ""
    )
    subs_section = (
        f"\n【ベンチ入り・想定交代カード】\n{substitutions_info}\n"
        if substitutions_info
        else ""
    )
    return f"""専門知識が少ないサッカーファンでも、スタジアムや画面の前で観戦を何倍も楽しめる観戦ガイドを生成してください。

【対戦カード・試合背景】
{match_facts}

【フォーメーション噛み合わせ】
{system_matchup}

【主要スタッツ】
{quantitative_summary}
{roles_section}{subs_section}
【指示】
{WATCHING_LENSES_GUIDE}
"""

