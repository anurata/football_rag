import 'package:flutter/material.dart';

import '../../../models/match_models.dart';

/// カード②: 選手詳細 (顔写真 / 通算CBP / 評点推移 / 事前インタビュー言説)
class PlayerDetailCard extends StatelessWidget {
  final PlayerContextItem? selectedPlayer;
  final int currentScore;
  final VoidCallback? onClearSelection;

  const PlayerDetailCard({
    super.key,
    this.selectedPlayer,
    this.currentScore = 0,
    this.onClearSelection,
  });

  @override
  Widget build(BuildContext context) {
    final player = selectedPlayer;
    if (player == null) {
      return Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: const Color(0xFF0F172A),
          borderRadius: BorderRadius.circular(10),
        ),
        child: const Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(Icons.touch_app_outlined, color: Colors.white38, size: 24),
              SizedBox(height: 6),
              Text(
                '下のピッチで選手ピンをダブルタップすると\n公式写真・事前インタビューが表示されます',
                textAlign: TextAlign.center,
                style: TextStyle(color: Colors.white54, fontSize: 11),
              ),
            ],
          ),
        ),
      );
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: const Color(0xFF0F172A),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: Colors.amber.withValues(alpha: 0.3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.spaceEvenly,
        children: [
          _buildHeaderRow(player),
          _buildStatsRow(player),
          _buildInterviewQuoteRow(player),
        ],
      ),
    );
  }

  Widget _buildHeaderRow(PlayerContextItem player) {
    return Row(
      children: [
        _buildAvatar(player),
        const SizedBox(width: 8),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Text(
                    '#${player.number} ${player.playerName}',
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 13,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(width: 6),
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 4,
                      vertical: 1,
                    ),
                    decoration: BoxDecoration(
                      color: Colors.white12,
                      borderRadius: BorderRadius.circular(3),
                    ),
                    child: Text(
                      player.position,
                      style: const TextStyle(
                        color: Colors.amberAccent,
                        fontSize: 9,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 2),
              Text(
                'ライブ観戦評価点: ${currentScore >= 0 ? "+$currentScore" : currentScore} pts',
                style: TextStyle(
                  color: currentScore >= 0 ? Colors.amber : Colors.blueAccent,
                  fontSize: 10,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
        ),
        if (onClearSelection != null)
          IconButton(
            icon: const Icon(Icons.close, size: 14, color: Colors.white38),
            padding: EdgeInsets.zero,
            constraints: const BoxConstraints(),
            onPressed: onClearSelection,
          ),
      ],
    );
  }

  Widget _buildAvatar(PlayerContextItem player) {
    return Container(
      width: 34,
      height: 34,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: Colors.grey[800],
        border: Border.all(color: Colors.amber, width: 1.2),
      ),
      child: ClipOval(
        child: player.photoUrl != null && player.photoUrl!.isNotEmpty
            ? Image.network(
                player.photoUrl!,
                fit: BoxFit.cover,
                errorBuilder: (context, error, stackTrace) =>
                    _buildFallbackIcon(),
              )
            : _buildFallbackIcon(),
      ),
    );
  }

  Widget _buildFallbackIcon() {
    return const Icon(Icons.person, size: 20, color: Colors.white54);
  }

  Widget _buildStatsRow(PlayerContextItem player) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: Colors.black26,
        borderRadius: BorderRadius.circular(6),
      ),
      child: const Row(
        mainAxisAlignment: MainAxisAlignment.spaceAround,
        children: [
          _StatMini(label: 'シーズン評点', value: '6.42'),
          _StatMini(label: '攻撃CBP', value: '14.2'),
          _StatMini(label: '守備CBP', value: '9.8'),
          _StatMini(label: 'パス成功率', value: '86%'),
        ],
      ),
    );
  }

  Widget _buildInterviewQuoteRow(PlayerContextItem player) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: Colors.amber.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: Colors.amber.withValues(alpha: 0.2)),
      ),
      child: Row(
        children: [
          const Icon(Icons.format_quote, size: 14, color: Colors.amber),
          const SizedBox(width: 4),
          Expanded(
            child: Text(
              '「相手のブロック間を突いて、サイドの幅を使って決定機を創出したい」 (試合前言説)',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.85),
                fontSize: 9.5,
                fontStyle: FontStyle.italic,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _StatMini extends StatelessWidget {
  final String label;
  final String value;

  const _StatMini({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text(
          label,
          style: const TextStyle(color: Colors.white38, fontSize: 8.5),
        ),
        const SizedBox(height: 1),
        Text(
          value,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 10.5,
            fontWeight: FontWeight.bold,
          ),
        ),
      ],
    );
  }
}
