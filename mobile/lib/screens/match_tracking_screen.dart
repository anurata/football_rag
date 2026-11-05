import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/action_models.dart';
import '../models/live_match_models.dart';
import '../models/match_models.dart';
import '../providers/match_provider.dart';
import '../widgets/action_ticker.dart';
import '../widgets/live/live_center_area.dart';
import '../widgets/pitch_board.dart';
import '../widgets/player_ranking_sheet.dart';
import '../widgets/position_swap_modal.dart';
import '../widgets/substitution_modal.dart';

class MatchTrackingScreen extends ConsumerStatefulWidget {
  final String matchId;

  const MatchTrackingScreen({
    super.key,
    this.matchId = '20261031_OKA_FCT',
  });

  @override
  ConsumerState<MatchTrackingScreen> createState() => _MatchTrackingScreenState();
}

class _MatchTrackingScreenState extends ConsumerState<MatchTrackingScreen> {
  final LiveSnapshotData _liveSnapshot = MockLiveSnapshot.getSample();
  PlayerContextItem? _selectedPlayer;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(matchTrackingProvider.notifier).loadMatch(widget.matchId);
    });
  }

  void _showMatchSelectSheet() async {
    final matches = await ref.read(apiClientProvider).fetchRecentMatches();
    if (!mounted) return;

    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.grey[900],
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) {
        return SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Padding(
                padding: EdgeInsets.all(16),
                child: Text(
                  '⚽ 試合を選択（DAZN観戦用）',
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.bold,
                    color: Colors.white,
                  ),
                ),
              ),
              Expanded(
                child: ListView.separated(
                  itemCount: matches.length,
                  separatorBuilder: (context, index) => const Divider(color: Colors.white12, height: 1),
                  itemBuilder: (context, index) {
                    final m = matches[index];
                    final hName = m['home_team_name'] ?? m['home_team_id'];
                    final aName = m['away_team_name'] ?? m['away_team_id'];
                    final mId = m['match_id'] as String;
                    final date = m['date'] ?? '';

                    return ListTile(
                      title: Text(
                        '$hName vs $aName',
                        style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.white),
                      ),
                      subtitle: Text(
                        '$date | $mId',
                        style: const TextStyle(fontSize: 11, color: Colors.white54),
                      ),
                      trailing: const Icon(Icons.chevron_right, color: Colors.white38),
                      onTap: () {
                        Navigator.pop(ctx);
                        ref.read(matchTrackingProvider.notifier).loadMatch(mId);
                      },
                    );
                  },
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  void _showSettingsDialog() {
    final currentUrl = ref.read(apiClientProvider).baseUrl;
    final controller = TextEditingController(text: currentUrl);

    showDialog(
      context: context,
      builder: (ctx) {
        return AlertDialog(
          title: const Text('APIサーバー設定'),
          content: TextField(
            controller: controller,
            decoration: const InputDecoration(
              labelText: 'FastAPI Base URL',
              hintText: 'http://127.0.0.1:8000',
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('キャンセル'),
            ),
            ElevatedButton(
              onPressed: () {
                ref.read(apiClientProvider).updateBaseUrl(controller.text.trim());
                Navigator.pop(ctx);
                ref.read(matchTrackingProvider.notifier).loadMatch(widget.matchId);
              },
              child: const Text('保存＆再接続'),
            ),
          ],
        );
      },
    );
  }

  void _showStopwatchSettingsDialog(
    BuildContext context,
    MatchTrackingNotifier notifier,
  ) {
    showDialog(
      context: context,
      builder: (ctx) {
        return AlertDialog(
          backgroundColor: Colors.grey[900],
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
          title: const Row(
            children: [
              Icon(Icons.timer_outlined, color: Colors.amber, size: 20),
              SizedBox(width: 8),
              Text(
                '試合タイマー設定',
                style: TextStyle(color: Colors.white, fontSize: 16),
              ),
            ],
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              ListTile(
                leading: const Icon(Icons.replay, color: Colors.blueAccent),
                title: const Text(
                  '前半開始 (00:00にリセット)',
                  style: TextStyle(color: Colors.white, fontSize: 14),
                ),
                subtitle: const Text(
                  '経過時間を0分0秒に戻します',
                  style: TextStyle(color: Colors.white54, fontSize: 11),
                ),
                onTap: () {
                  HapticFeedback.mediumImpact();
                  notifier.setElapsedSeconds(0);
                  Navigator.pop(ctx);
                },
              ),
              const Divider(color: Colors.white24, height: 1),
              ListTile(
                leading: const Icon(Icons.fast_forward, color: Colors.amberAccent),
                title: const Text(
                  '後半開始 (45:00に設定)',
                  style: TextStyle(color: Colors.white, fontSize: 14),
                ),
                subtitle: const Text(
                  '経過時間を45分0秒に設定します',
                  style: TextStyle(color: Colors.white54, fontSize: 11),
                ),
                onTap: () {
                  HapticFeedback.mediumImpact();
                  notifier.setElapsedSeconds(45 * 60);
                  Navigator.pop(ctx);
                },
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('キャンセル', style: TextStyle(color: Colors.white54)),
            ),
          ],
        );
      },
    );
  }

  void _showDeleteActionDialog(
    UserAction action,
    MatchTrackingNotifier notifier,
  ) {
    final name = action.playerName ?? action.playerId;
    final typeLabel = action.actionType == 'good' ? '👍 Good' : '👎 Bad';
    final bonusText = action.bonusPoints > 0 ? ' (+${action.bonusPoints}点)' : '';

    showDialog(
      context: context,
      builder: (ctx) {
        return AlertDialog(
          backgroundColor: Colors.grey[900],
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
          title: const Text(
            'アクションの削除',
            style: TextStyle(color: Colors.white, fontSize: 16),
          ),
          content: Text(
            "${action.matchMinute}' $name の評価 ($typeLabel$bonusText) を削除しますか？\n選手の点数も元に戻ります。",
            style: const TextStyle(color: Colors.white70, fontSize: 13),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('キャンセル', style: TextStyle(color: Colors.white54)),
            ),
            ElevatedButton(
              style: ElevatedButton.styleFrom(backgroundColor: Colors.red[700]),
              onPressed: () {
                notifier.removeAction(action.id);
                Navigator.pop(ctx);
              },
              child: const Text('削除する', style: TextStyle(color: Colors.white)),
            ),
          ],
        );
      },
    );
  }

  void _showSubstitutionModal(TeamContextItem team, bool isHome) {
    SubstitutionModal.show(
      context: context,
      team: team,
      isHome: isHome,
      onConfirm: (outPlayerId, inPlayerId) {
        ref.read(matchTrackingProvider.notifier).substitutePlayer(
              teamId: team.teamId,
              outPlayerId: outPlayerId,
              inPlayerId: inPlayerId,
            );
      },
    );
  }

  void _showPositionSwapModal(TeamContextItem team, bool isHome) {
    PositionSwapModal.show(
      context: context,
      team: team,
      isHome: isHome,
      onConfirm: (p1Id, p2Id) {
        ref.read(matchTrackingProvider.notifier).swapPositions(
              teamId: team.teamId,
              player1Id: p1Id,
              player2Id: p2Id,
            );
      },
    );
  }

  void _showPlayerRankingSheet(TeamContextItem team, bool isHome) {
    final rankings = ref.read(matchTrackingProvider.notifier).getRankings(
          teamId: team.teamId,
        );
    PlayerRankingSheet.show(
      context: context,
      team: team,
      isHome: isHome,
      rankings: rankings,
    );
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(matchTrackingProvider);
    final notifier = ref.read(matchTrackingProvider.notifier);

    if (state.isLoading && state.matchContext == null) {
      return const Scaffold(
        backgroundColor: Colors.black,
        body: Center(
          child: CircularProgressIndicator(color: Colors.green),
        ),
      );
    }

    final match = state.matchContext;
    if (match == null) {
      return const Scaffold(
        backgroundColor: Colors.black,
        body: Center(
          child: Text('試合データが見つかりません', style: TextStyle(color: Colors.white)),
        ),
      );
    }

    final isHome = state.selectedTeam == 'HOME';
    final currentTeam = isHome ? match.homeTeam : match.awayTeam;

    return Scaffold(
      backgroundColor: Colors.black,
      appBar: _buildAppBar(match),
      body: Column(
        children: [
          Expanded(
            child: LiveCenterArea(
              snapshot: _liveSnapshot,
              userActions: state.recentActions,
              selectedPlayer: _selectedPlayer,
              selectedPlayerScore: _selectedPlayer != null
                  ? (state.playerScores[_selectedPlayer!.playerId] ?? 0)
                  : 0,
              homeTeamName: match.homeTeam.shortName,
              awayTeamName: match.awayTeam.shortName,
              onClearSelectedPlayer: () {
                setState(() => _selectedPlayer = null);
              },
              onOpenWebDetails: () {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(
                    content: Text('🌐 Web詳細カルテへ遷移（実装予定）'),
                    duration: Duration(seconds: 1),
                  ),
                );
              },
              onSpeakTweet: () {
                HapticFeedback.mediumImpact();
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(
                    content: Text(
                      '🔊 [TTS読み上げ] ${_liveSnapshot.latestAiTweet?.text ?? ""}',
                    ),
                    duration: const Duration(seconds: 2),
                  ),
                );
              },
              onAskLlm: () {
                HapticFeedback.mediumImpact();
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(
                    content: Text('💬 戦術質問ダイアログ（実装予定）'),
                    duration: Duration(seconds: 1),
                  ),
                );
              },
            ),
          ),
          SizedBox(
            height: 362,
            child: PitchBoard(
              team: currentTeam,
              isHome: isHome,
              playerScores: state.playerScores,
              playerLiveStatus: {
                for (final e in _liveSnapshot.playerLiveStatus.entries)
                  e.key: e.value.status,
              },
              onPlayerDoubleTap: (player) {
                HapticFeedback.mediumImpact();
                setState(() => _selectedPlayer = player);
              },
              onSubstituteTap: () => _showSubstitutionModal(currentTeam, isHome),
              onSwapPositionsTap: () => _showPositionSwapModal(currentTeam, isHome),
              onShowRankingsTap: () => _showPlayerRankingSheet(currentTeam, isHome),
              onPlayerAction: (player, actionType, category) {
                notifier.recordAction(
                  playerId: player.playerId,
                  playerName: player.playerName,
                  teamId: currentTeam.teamId,
                  actionType: actionType,
                  playCategory: category,
                );
              },
            ),
          ),
          _buildTeamToggleBar(match, isHome, notifier),
          ActionTicker(
            currentMinute: state.currentMinute,
            formattedTime: state.formattedTime,
            isTimerRunning: state.isTimerRunning,
            isOver45Minutes: state.isOver45Minutes,
            recentActions: state.recentActions,
            syncStatus: state.syncStatusMessage,
            onIncrementMinute: () => notifier.adjustMinutes(1),
            onDecrementMinute: () => notifier.adjustMinutes(-1),
            onToggleTimer: () {
              HapticFeedback.mediumImpact();
              notifier.toggleTimer();
            },
            onLongPressTimer: () {
              HapticFeedback.heavyImpact();
              _showStopwatchSettingsDialog(context, notifier);
            },
            onTapAction: (action) {
              HapticFeedback.mediumImpact();
              notifier.incrementActionBonus(action.id);
            },
            onLongPressAction: (action) {
              HapticFeedback.heavyImpact();
              _showDeleteActionDialog(action, notifier);
            },
          ),
        ],
      ),
    );
  }

  PreferredSizeWidget _buildAppBar(MatchAppContext match) {
    return AppBar(
      backgroundColor: Colors.grey[900],
      elevation: 0,
      title: GestureDetector(
        onTap: _showMatchSelectSheet,
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              match.homeTeam.shortName,
              style: const TextStyle(fontSize: 14, fontWeight: FontWeight.bold),
            ),
            const SizedBox(width: 6),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
              decoration: BoxDecoration(
                color: Colors.black87,
                borderRadius: BorderRadius.circular(4),
              ),
              child: Text(
                '${match.homeTeam.score} - ${match.awayTeam.score}',
                style: const TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.bold,
                  color: Colors.amber,
                ),
              ),
            ),
            const SizedBox(width: 6),
            Text(
              match.awayTeam.shortName,
              style: const TextStyle(fontSize: 14, fontWeight: FontWeight.bold),
            ),
            const SizedBox(width: 4),
            const Icon(Icons.arrow_drop_down, size: 18, color: Colors.white70),
          ],
        ),
      ),
      centerTitle: true,
      actions: [
        IconButton(
          icon: const Icon(Icons.settings, size: 20),
          onPressed: _showSettingsDialog,
        ),
        IconButton(
          icon: const Icon(Icons.refresh, size: 20),
          onPressed: () {
            ref.read(matchTrackingProvider.notifier).loadMatch(widget.matchId);
          },
        ),
      ],
    );
  }



  Widget _buildTeamToggleBar(
    MatchAppContext match,
    bool isHome,
    MatchTrackingNotifier notifier,
  ) {
    return Container(
      color: Colors.grey[900],
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      child: Row(
        children: [
          Expanded(
            child: _buildTeamButton(
              title: '${match.homeTeam.shortName} (HOME)',
              isSelected: isHome,
              color: const Color(0xFF1E40AF), // Tokyo blue
              onTap: () => notifier.switchTeam('HOME'),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: _buildTeamButton(
              title: '${match.awayTeam.shortName} (AWAY)',
              isSelected: !isHome,
              color: const Color(0xFFDC2626), // Away red
              onTap: () => notifier.switchTeam('AWAY'),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTeamButton({
    required String title,
    required bool isSelected,
    required Color color,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        padding: const EdgeInsets.symmetric(vertical: 8),
        decoration: BoxDecoration(
          color: isSelected ? color : Colors.white10,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(
            color: isSelected ? Colors.white : Colors.transparent,
            width: 1.5,
          ),
        ),
        child: Center(
          child: Text(
            title,
            style: TextStyle(
              fontSize: 12,
              fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
              color: isSelected ? Colors.white : Colors.white70,
            ),
          ),
        ),
      ),
    );
  }
}
