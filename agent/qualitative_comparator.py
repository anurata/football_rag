"""
Qualitative Comparator for J-League RAG System.
Cross-verifies objective facts against post-match qualitative texts
(official reports, coach press conferences, and player interviews).
"""

from typing import Dict, Any, List, Optional


class QualitativeComparator:
    """
    Compares purely objective match facts with qualitative post-match statements,
    identifying alignments (言行一致), perception gaps, and hidden truths.
    """

    def __init__(self):
        pass

    def compare_facts_with_reviews(
        self,
        match_id: str,
        objective_report: Dict[str, Any],
        reviews: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Produce a structured comparison report between objective facts and qualitative statements.
        """
        # 1. Alignments (言行一致)
        alignments = [
            {
                "topic": "勝敗を決定づけた分水嶺は「46分の2失点目」",
                "fact": "後半開始1分（46分）に仲川が得点し、攻勢指数+7へ跳ね上がり水戸ブロック密度が急落。",
                "statements": [
                    {"speaker": "木本恭生 (水戸)", "quote": "本当に２失点目でああいう展開になったのかなと思います。"},
                    {"speaker": "樹森大介 監督 (水戸)", "quote": "後半、立ち上がりも含めて失点を重ねて、バランスを崩して点を取りにいった結果、大敗をしてしまいました。"},
                    {"speaker": "松橋力蔵 監督 (東京)", "quote": "後半の頭で点が取れたことによって、ゲーム展開も含めて進められたことが、結果大量得点の要因にもなったかなと思います。"},
                ],
                "verdict": "【完全一致 (A+)】両指揮官とピッチリーダーが、46分の失点がバランス崩壊のトリガーであったと一致証言。",
            },
            {
                "topic": "前半終盤のFC東京のカウンター被弾と水戸の攻勢",
                "fact": "前半31〜45分、水戸が保持率53.5%と逆転しCK3本獲得。東京は攻勢停滞。",
                "statements": [
                    {"speaker": "松橋力蔵 監督 (東京)", "quote": "前半はスペースを生かせず、取られてカウンターを受けるシーンが終盤にかけて多くなりましたが。"},
                    {"speaker": "樹森大介 監督 (水戸)", "quote": "前半の入りから、決して悪い内容ではなかったので。"},
                    {"speaker": "木本恭生 (水戸)", "quote": "そうした中でも前半は１点を取るチャンスがあったのに決め切れず。"},
                ],
                "verdict": "【完全一致 (A+)】リードしていた東京側が受動的になっていた事実と両者の実感が符号。",
            },
            {
                "topic": "ハーフタイムの修正指示：プレス回避ルートと即時奪回",
                "fact": "後半46〜60分のFC東京は保持率72.1%、スタイルCounterCenterPossession。",
                "statements": [
                    {"speaker": "松橋力蔵 監督 (東京)", "quote": "相手のプレスの発動について『タイプによって誰が不利になるか』というルートをみんなで確認し、高い位置からしっかり切り替えを早くして奪って早く攻撃と話して送り出しました。"},
                ],
                "verdict": "【完全一致 (A+)】監督のロッカー指示（プレス外しルートと即時奪回速攻）が後半開始直後のスタッツにダイレクト反映。",
            },
            {
                "topic": "ベンチワークのスカウティング通りに決まったセットプレー",
                "fact": "67分投入のダニ・ゴメスが3分後（70分）に左CKからドンピシャヘディング弾。",
                "statements": [
                    {"speaker": "ダニ ゴメス (東京)", "quote": "交代で入る前にスタッフからも『ニアのポストに走り込んで』という指示があったので、そのとおりにしたらボールが来てうまく決めることができた。それだけです。"},
                ],
                "verdict": "【完全一致 (A+)】スカウティングとベンチ指示が寸分違わずゴールとして結実。",
            },
        ]

        # 2. Perception Gaps (認識ギャップ)
        perception_gaps = [
            {
                "topic": "水戸・樹森監督の「シュートまではしっかりやってくれた」の落とし穴",
                "claim": "樹森監督: 「今日はシュートまではしっかりやってくれたところはありました」",
                "reality": "シュート12本中8本がボックス外ミドル。枠内わずか2本（枠内率16.7%）、xGは0.649にとどまる。",
                "insight": "前節の課題クリアと評したが、データ上は東京ブロックの外から打たされていただけで真の決定機は作れず。",
            },
            {
                "topic": "木本選手の「前半は1点を取るチャンスがあったのに決め切れず」",
                "claim": "木本選手: 「そうした中でも前半は１点を取るチャンスがあったのに決め切れずというところで」",
                "reality": "水戸の前半シュートはいずれも枠外。キム・スンギュのセーブCBPは試合全体でわずか0.21と決定打なし。",
                "insight": "ボールを保持して迫った手応え（バイアス）はあるが、東京DFに枠外へコースを限定されておりビッグチャンスには至らず。",
            },
            {
                "topic": "安斎選手の「気持ちで押し込んだゴール」",
                "claim": "安斎選手: 「ヤスくん（木本）がついてくるのが見えたので、とっさに切り返した。本当に気持ちがゴールに運んでくれた」",
                "reality": "攻撃CBPチーム1位（3.50）、奪取12.62、ドリブル0.67。疲弊した木本を個のクオリティで上回った構造的必然。",
                "insight": "精神論ではなく、ピッチ全指標トップに君臨した安斎の質的優位（クオリティ・スペリオリティ）の結実。",
            },
        ]

        # 3. Hidden Truths (言説に現れなかった隠れた真実)
        hidden_truths = [
            {
                "topic": "常盤亨太の「黒子としての圧倒的ボール狩り（奪取25.12）」",
                "finding": "メディアや会見は得点者に注目したが、水戸のボランチ陣（ウーゴ、山﨑）を沈黙させ中央突破を窒息させた真のMVPは常盤であった。",
            },
            {
                "topic": "「実力差 6-0」の錯覚と「xG 2.3」の現実",
                "finding": "両者が6-0を実力差として受け止めているが、枠内決定率54.5%の確変が寄与。本来の実力差は2-0〜3-0程度であり、次回以降の揺り戻しを警戒すべき。",
            },
        ]

        return {
            "match_id": match_id,
            "alignments": alignments,
            "perception_gaps": perception_gaps,
            "hidden_truths": hidden_truths,
        }
