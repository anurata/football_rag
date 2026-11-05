import 'package:flutter/material.dart';

import '../../models/action_models.dart';
import '../../models/live_match_models.dart';
import '../../models/match_models.dart';
import 'cards/ai_commentary_card.dart';
import 'cards/club_target_card.dart';
import 'cards/live_raw_list_card.dart';
import 'cards/momentum_card.dart';
import 'cards/player_detail_card.dart';
import 'cards/team_stats_card.dart';
import 'live_alert_banner.dart';

/// センターエリア親コンポーネント: PageView 6大カード ＆ 上部通知バナー
class LiveCenterArea extends StatefulWidget {
  final LiveSnapshotData snapshot;
  final List<UserAction> userActions;
  final PlayerContextItem? selectedPlayer;
  final int selectedPlayerScore;
  final String homeTeamName;
  final String awayTeamName;
  final VoidCallback? onClearSelectedPlayer;
  final VoidCallback? onOpenWebDetails;
  final VoidCallback? onSpeakTweet;
  final VoidCallback? onAskLlm;

  const LiveCenterArea({
    super.key,
    required this.snapshot,
    required this.userActions,
    this.selectedPlayer,
    this.selectedPlayerScore = 0,
    this.homeTeamName = '岡山',
    this.awayTeamName = 'FC東京',
    this.onClearSelectedPlayer,
    this.onOpenWebDetails,
    this.onSpeakTweet,
    this.onAskLlm,
  });

  @override
  State<LiveCenterArea> createState() => LiveCenterAreaState();
}

class LiveCenterAreaState extends State<LiveCenterArea> {
  late final PageController _pageController;
  int _currentPage = 0;
  bool _isAlertDismissed = false;

  static const List<String> _cardTitles = [
    'チームスタッツ',
    '選手詳細',
    'モメンタム',
    'クラブの狙い',
    'AIつぶやき',
    '速報生ログ',
  ];

  @override
  void initState() {
    super.initState();
    final initialPage = widget.selectedPlayer != null ? 1 : 0;
    _currentPage = initialPage;
    _pageController = PageController(initialPage: initialPage);
  }

  @override
  void didUpdateWidget(covariant LiveCenterArea oldWidget) {
    super.didUpdateWidget(oldWidget);
    // 選手ピンがダブルタップされて選手が選ばれた場合、自動で「選手詳細カード (index 1)」へジャンプ
    if (widget.selectedPlayer != null &&
        widget.selectedPlayer?.playerId != oldWidget.selectedPlayer?.playerId) {
      jumpToPage(1);
    }
  }

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  /// 外部または通知タップから任意のページへスムーズにジャンプ
  void jumpToPage(int pageIndex) {
    if (_pageController.hasClients) {
      _pageController.animateToPage(
        pageIndex,
        duration: const Duration(milliseconds: 300),
        curve: Curves.easeInOut,
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final alert = widget.snapshot.timelineAlert;
    final showAlert =
        alert != null && alert.active && !_isAlertDismissed;

    return Container(
      width: double.infinity,
      margin: const EdgeInsets.fromLTRB(10, 4, 10, 4),
      padding: const EdgeInsets.fromLTRB(10, 8, 10, 6),
      decoration: BoxDecoration(
        color: const Color(0xFF1E293B),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: Colors.blueGrey.withValues(alpha: 0.35),
          width: 1,
        ),
      ),
      child: Column(
        children: [
          if (showAlert)
            LiveAlertBanner(
              alert: alert,
              onTap: () => jumpToPage(4), // AIつぶやき/解説カードへジャンプ
              onClose: () => setState(() => _isAlertDismissed = true),
            ),
          _buildTabBarHeader(),
          const SizedBox(height: 6),
          Expanded(
            child: PageView(
              controller: _pageController,
              onPageChanged: (idx) => setState(() => _currentPage = idx),
              children: [
                // 1. チームスタッツ
                TeamStatsCard(
                  metrics: widget.snapshot.metrics,
                  homeName: widget.homeTeamName,
                  awayName: widget.awayTeamName,
                ),
                // 2. 選手詳細
                PlayerDetailCard(
                  selectedPlayer: widget.selectedPlayer,
                  currentScore: widget.selectedPlayerScore,
                  onClearSelection: widget.onClearSelectedPlayer,
                ),
                // 3. モメンタム ✕ 感情ログ
                MomentumCard(
                  actions: widget.userActions,
                  currentMinute: widget.snapshot.elapsedMinute,
                ),
                // 4. クラブの狙い
                ClubTargetCard(
                  teamName: widget.awayTeamName,
                  onOpenWebDetails: widget.onOpenWebDetails,
                ),
                // 5. AI解説 ✕ つぶやきタイムライン
                AiCommentaryCard(
                  tweet: widget.snapshot.latestAiTweet,
                  onSpeakTap: widget.onSpeakTweet,
                  onAskLlmTap: widget.onAskLlm,
                ),
                // 6. 速報生リスト
                LiveRawListCard(
                  events: widget.snapshot.rawEvents,
                ),
              ],
            ),
          ),
          const SizedBox(height: 6),
          _buildPageIndicator(),
        ],
      ),
    );
  }

  Widget _buildTabBarHeader() {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Row(
          children: [
            const Icon(Icons.bolt, color: Colors.amber, size: 14),
            const SizedBox(width: 4),
            Text(
              _cardTitles[_currentPage],
              style: const TextStyle(
                color: Colors.amber,
                fontSize: 11,
                fontWeight: FontWeight.bold,
                letterSpacing: 0.3,
              ),
            ),
          ],
        ),
        Row(
          children: [
            Text(
              '${_currentPage + 1} / ${_cardTitles.length}',
              style: const TextStyle(color: Colors.white38, fontSize: 10),
            ),
            const SizedBox(width: 4),
            const Icon(Icons.swipe, color: Colors.white38, size: 12),
          ],
        ),
      ],
    );
  }

  Widget _buildPageIndicator() {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: List.generate(_cardTitles.length, (idx) {
        final isActive = idx == _currentPage;
        return AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          margin: const EdgeInsets.symmetric(horizontal: 2.5),
          width: isActive ? 14 : 5,
          height: 4,
          decoration: BoxDecoration(
            color: isActive ? Colors.amber : Colors.white24,
            borderRadius: BorderRadius.circular(2),
          ),
        );
      }),
    );
  }
}
