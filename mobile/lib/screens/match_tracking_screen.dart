import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/match_models.dart';
import '../providers/match_provider.dart';
import '../widgets/action_ticker.dart';
import '../widgets/pitch_board.dart';

class MatchTrackingScreen extends ConsumerStatefulWidget {
  final String matchId;

  const MatchTrackingScreen({
    super.key,
    this.matchId = '2026_M01_FCT_ZEL',
  });

  @override
  ConsumerState<MatchTrackingScreen> createState() => _MatchTrackingScreenState();
}

class _MatchTrackingScreenState extends ConsumerState<MatchTrackingScreen> {
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
            child: _buildLiveNewsPlaceholder(match),
          ),
          SizedBox(
            height: 330,
            child: PitchBoard(
              team: currentTeam,
              isHome: isHome,
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
            recentActions: state.recentActions,
            syncStatus: state.syncStatusMessage,
            onIncrementMinute: () => notifier.incrementMinute(),
            onDecrementMinute: () {
              if (state.currentMinute > 0) {
                notifier.setMinute(state.currentMinute - 1);
              }
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

  Widget _buildLiveNewsPlaceholder(MatchAppContext match) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.fromLTRB(10, 6, 10, 6),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFF1E293B),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
          color: Colors.blueGrey.withValues(alpha: 0.35),
          width: 1,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.bolt, color: Colors.amber, size: 16),
              SizedBox(width: 6),
              Text(
                'LIVE MATCH FEED & TACTICAL INFO',
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.bold,
                  letterSpacing: 0.5,
                  color: Colors.amber,
                ),
              ),
              Spacer(),
              Icon(Icons.expand_more, color: Colors.white38, size: 16),
            ],
          ),
          const SizedBox(height: 8),
          Expanded(
            child: Container(
              width: double.infinity,
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: Colors.black26,
                borderRadius: BorderRadius.circular(8),
              ),
              child: const Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text(
                    '中央試合情報表示エリア（中身は後で実装）',
                    style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.bold,
                      color: Colors.white,
                    ),
                  ),
                  SizedBox(height: 6),
                  Text(
                    '• ゴール速報・ハイライトイベント\n• xG推移・ボール支配率・シュートスタッツ\n• AI戦術インサイト・モメンタム速報',
                    style: TextStyle(
                      fontSize: 11,
                      color: Colors.white60,
                      height: 1.45,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
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
