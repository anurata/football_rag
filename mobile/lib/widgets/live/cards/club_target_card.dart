import 'package:flutter/material.dart';

/// カード④: クラブの狙い達成度 & 通算戦績 & Web詳細導線
class ClubTargetCard extends StatelessWidget {
  final String teamName;
  final int planProgress; // 0 - 100%
  final String planTitle;
  final String recentForm;
  final VoidCallback? onOpenWebDetails;

  const ClubTargetCard({
    super.key,
    this.teamName = 'FC東京',
    this.planProgress = 72,
    this.planTitle = 'プランA: 敵陣奪取からのハイプレス＆ショートカウンター',
    this.recentForm = 'W D W W L',
    this.onOpenWebDetails,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: const Color(0xFF0F172A),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.spaceEvenly,
        children: [
          _buildHeaderRow(),
          _buildPlanProgressRow(),
          _buildFormAndWebButtonRow(),
        ],
      ),
    );
  }

  Widget _buildHeaderRow() {
    return Row(
      children: [
        const Icon(Icons.track_changes, color: Colors.lightGreenAccent, size: 14),
        const SizedBox(width: 6),
        Text(
          '$teamName の戦術プラン達成度',
          style: const TextStyle(
            color: Colors.lightGreenAccent,
            fontSize: 11,
            fontWeight: FontWeight.bold,
          ),
        ),
        const Spacer(),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1.5),
          decoration: BoxDecoration(
            color: Colors.lightGreenAccent.withValues(alpha: 0.15),
            borderRadius: BorderRadius.circular(4),
          ),
          child: Text(
            '達成率 $planProgress%',
            style: const TextStyle(
              color: Colors.lightGreenAccent,
              fontSize: 10,
              fontWeight: FontWeight.bold,
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildPlanProgressRow() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          planTitle,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(color: Colors.white70, fontSize: 10),
        ),
        const SizedBox(height: 3),
        ClipRRect(
          borderRadius: BorderRadius.circular(3),
          child: LinearProgressIndicator(
            value: (planProgress / 100.0).clamp(0.0, 1.0),
            minHeight: 5,
            backgroundColor: Colors.white12,
            valueColor: const AlwaysStoppedAnimation<Color>(
              Colors.lightGreenAccent,
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildFormAndWebButtonRow() {
    return Row(
      children: [
        const Text(
          '直近フォルム: ',
          style: TextStyle(color: Colors.white54, fontSize: 9.5),
        ),
        _buildFormBadges(recentForm),
        const Spacer(),
        InkWell(
          onTap: onOpenWebDetails,
          borderRadius: BorderRadius.circular(4),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
            decoration: BoxDecoration(
              color: Colors.blueAccent.withValues(alpha: 0.2),
              borderRadius: BorderRadius.circular(4),
              border: Border.all(
                color: Colors.blueAccent.withValues(alpha: 0.4),
              ),
            ),
            child: const Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.public, color: Colors.blueAccent, size: 12),
                SizedBox(width: 4),
                Text(
                  'Web戦術カルテへ',
                  style: TextStyle(
                    color: Colors.blueAccent,
                    fontSize: 9.5,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildFormBadges(String form) {
    final list = form.split(' ');
    return Row(
      children: list.map((item) {
        Color c;
        if (item == 'W') {
          c = Colors.greenAccent;
        } else if (item == 'D') {
          c = Colors.amberAccent;
        } else {
          c = Colors.redAccent;
        }

        return Container(
          margin: const EdgeInsets.only(right: 3),
          padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 0.5),
          decoration: BoxDecoration(
            color: c.withValues(alpha: 0.2),
            borderRadius: BorderRadius.circular(2),
          ),
          child: Text(
            item,
            style: TextStyle(
              color: c,
              fontSize: 8.5,
              fontWeight: FontWeight.bold,
            ),
          ),
        );
      }).toList(),
    );
  }
}
