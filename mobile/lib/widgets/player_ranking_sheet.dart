import 'package:flutter/material.dart';

import '../models/match_models.dart';
import 'player_pin.dart';

/// Bottom sheet displaying the in-match player evaluation rankings.
class PlayerRankingSheet extends StatelessWidget {
  final TeamContextItem team;
  final bool isHome;
  final List<PlayerRankingEntry> rankings;

  const PlayerRankingSheet({
    super.key,
    required this.team,
    required this.isHome,
    required this.rankings,
  });

  static Future<void> show({
    required BuildContext context,
    required TeamContextItem team,
    required bool isHome,
    required List<PlayerRankingEntry> rankings,
  }) {
    return showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: const Color(0xFF0F172A),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) => PlayerRankingSheet(
        team: team,
        isHome: isHome,
        rankings: rankings,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final sheetHeight = MediaQuery.of(context).size.height * 0.75;

    return SafeArea(
      child: Container(
        height: sheetHeight,
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _buildHeader(context),
            const SizedBox(height: 8),
            _buildSubtitle(),
            const SizedBox(height: 12),
            Expanded(
              child: _buildRankingsList(),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader(BuildContext context) {
    return Row(
      children: [
        const Icon(Icons.leaderboard, color: Colors.lightGreenAccent, size: 22),
        const SizedBox(width: 8),
        Text(
          '選手評価ランキング - ${team.shortName}',
          style: const TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.bold,
            color: Colors.white,
          ),
        ),
        const Spacer(),
        IconButton(
          visualDensity: VisualDensity.compact,
          icon: const Icon(Icons.close, color: Colors.white54, size: 20),
          onPressed: () => Navigator.pop(context),
        ),
      ],
    );
  }

  Widget _buildSubtitle() {
    return const Text(
      '観戦中に記録されたGood/Bad評価・加点に基づくリアルタイムランキング',
      style: TextStyle(
        fontSize: 11,
        color: Colors.white60,
      ),
    );
  }

  Widget _buildRankingsList() {
    if (rankings.isEmpty) {
      return const Center(
        child: Text(
          '選手データがありません',
          style: TextStyle(color: Colors.white38, fontSize: 13),
        ),
      );
    }

    return ListView.separated(
      itemCount: rankings.length,
      separatorBuilder: (context, index) => const Divider(
        color: Colors.white12,
        height: 1,
      ),
      itemBuilder: (context, index) {
        final entry = rankings[index];
        return _buildRankingItem(entry);
      },
    );
  }

  Widget _buildRankingItem(PlayerRankingEntry entry) {
    final isTop3 = entry.rank <= 3 && entry.actionCount > 0;

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        children: [
          _buildRankBadge(entry.rank, isTop3),
          const SizedBox(width: 10),
          _buildPlayerNumberCircle(entry.player, entry.netScore),
          const SizedBox(width: 10),
          Expanded(
            child: _buildPlayerInfo(entry),
          ),
          const SizedBox(width: 8),
          _buildScoreColumn(entry),
        ],
      ),
    );
  }

  Widget _buildRankBadge(int rank, bool isTop3) {
    Color badgeColor = Colors.white38;
    String rankLabel = '$rank';

    if (isTop3) {
      if (rank == 1) {
        badgeColor = const Color(0xFFFFD700); // Gold
        rankLabel = '🥇';
      } else if (rank == 2) {
        badgeColor = const Color(0xFFC0C0C0); // Silver
        rankLabel = '🥈';
      } else if (rank == 3) {
        badgeColor = const Color(0xFFCD7F32); // Bronze
        rankLabel = '🥉';
      }
    }

    return SizedBox(
      width: 28,
      child: Center(
        child: Text(
          rankLabel,
          style: TextStyle(
            fontSize: isTop3 ? 16 : 13,
            fontWeight: FontWeight.bold,
            color: badgeColor,
          ),
        ),
      ),
    );
  }

  Widget _buildPlayerNumberCircle(PlayerContextItem player, int netScore) {
    final circleColor = PlayerPin.calculateScoreBadgeColor(netScore, isHome: isHome);

    return Container(
      width: 28,
      height: 28,
      decoration: BoxDecoration(
        color: circleColor,
        shape: BoxShape.circle,
        border: Border.all(
          color: Colors.white38,
          width: 1,
        ),
      ),
      child: Center(
        child: Text(
          '${player.number}',
          style: const TextStyle(
            fontSize: 12,
            fontWeight: FontWeight.bold,
            color: Colors.white,
          ),
        ),
      ),
    );
  }

  Widget _buildPlayerInfo(PlayerRankingEntry entry) {
    final p = entry.player;
    final posBg = p.isStarter ? const Color(0xFF1E3A8A) : Colors.grey[800]!;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text(
              p.displayName,
              style: const TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.bold,
                color: Colors.white,
              ),
            ),
            const SizedBox(width: 6),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 1),
              decoration: BoxDecoration(
                color: posBg,
                borderRadius: BorderRadius.circular(4),
              ),
              child: Text(
                p.position,
                style: const TextStyle(
                  fontSize: 9,
                  fontWeight: FontWeight.bold,
                  color: Colors.white70,
                ),
              ),
            ),
            if (!p.isStarter) ...[
              const SizedBox(width: 4),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 1),
                decoration: BoxDecoration(
                  color: Colors.amber[900],
                  borderRadius: BorderRadius.circular(4),
                ),
                child: const Text(
                  '控え',
                  style: TextStyle(
                    fontSize: 8,
                    fontWeight: FontWeight.bold,
                    color: Colors.white,
                  ),
                ),
              ),
            ],
          ],
        ),
        const SizedBox(height: 3),
        Row(
          children: [
            _buildDetailTag('👍 +${entry.positivePoints}', Colors.greenAccent),
            const SizedBox(width: 6),
            _buildDetailTag('👎 -${entry.negativePoints}', Colors.redAccent),
            const SizedBox(width: 6),
            _buildDetailTag('計 ${entry.actionCount}件', Colors.white38),
          ],
        ),
      ],
    );
  }

  Widget _buildDetailTag(String text, Color color) {
    return Text(
      text,
      style: TextStyle(
        fontSize: 10,
        fontWeight: FontWeight.w500,
        color: color,
      ),
    );
  }

  Widget _buildScoreColumn(PlayerRankingEntry entry) {
    final score = entry.netScore;
    final isPositive = score > 0;
    final isNegative = score < 0;

    final scoreColor = isPositive
        ? Colors.amberAccent
        : (isNegative ? Colors.redAccent : Colors.white54);
    final prefix = isPositive ? '+' : '';

    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        Text(
          '$prefix$score',
          style: TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.bold,
            color: scoreColor,
          ),
        ),
        const Text(
          'PTS',
          style: TextStyle(
            fontSize: 8,
            fontWeight: FontWeight.bold,
            color: Colors.white38,
            letterSpacing: 0.5,
          ),
        ),
      ],
    );
  }
}
