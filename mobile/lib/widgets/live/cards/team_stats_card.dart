import 'package:flutter/material.dart';

import '../../../models/live_match_models.dart';

/// カード①: チームスタッツ (Field Tilt / PPDA / PA進入方向 / xG品質)
class TeamStatsCard extends StatelessWidget {
  final TeamLiveMetrics metrics;
  final String homeName;
  final String awayName;

  const TeamStatsCard({
    super.key,
    required this.metrics,
    this.homeName = '岡山',
    this.awayName = 'FC東京',
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
          _buildFieldTiltRow(),
          _buildPpdaAndPaRow(),
          _buildShotQualityRow(),
        ],
      ),
    );
  }

  Widget _buildHeaderRow() {
    return const Row(
      children: [
        Icon(Icons.analytics_outlined, color: Colors.cyanAccent, size: 14),
        SizedBox(width: 6),
        Text(
          'リアルタイム戦術スタッツ',
          style: TextStyle(
            color: Colors.cyanAccent,
            fontSize: 11,
            fontWeight: FontWeight.bold,
          ),
        ),
        Spacer(),
        Text(
          '直近15分',
          style: TextStyle(
            color: Colors.white38,
            fontSize: 10,
          ),
        ),
      ],
    );
  }

  Widget _buildFieldTiltRow() {
    final homePct = (metrics.homeFieldTilt * 100).round();
    final awayPct = 100 - homePct;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text(
              '$homeName $homePct%',
              style: const TextStyle(
                color: Color(0xFFF87171),
                fontSize: 10.5,
                fontWeight: FontWeight.bold,
              ),
            ),
            const Expanded(
              child: Text(
                '押し込み度 (Field Tilt)',
                textAlign: TextAlign.center,
                style: TextStyle(color: Colors.white70, fontSize: 9.5),
              ),
            ),
            Text(
              '$awayPct% $awayName',
              style: const TextStyle(
                color: Color(0xFF60A5FA),
                fontSize: 10.5,
                fontWeight: FontWeight.bold,
              ),
            ),
          ],
        ),
        const SizedBox(height: 3),
        ClipRRect(
          borderRadius: BorderRadius.circular(4),
          child: SizedBox(
            height: 6,
            child: Row(
              children: [
                Expanded(
                  flex: homePct,
                  child: Container(color: const Color(0xFFEF4444)),
                ),
                Expanded(
                  flex: awayPct,
                  child: Container(color: const Color(0xFF3B82F6)),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildPpdaAndPaRow() {
    return Row(
      children: [
        Expanded(
          child: _buildMetricTile(
            label: 'プレス強度 (PPDA)',
            value: '${metrics.homeProxyPpda} / ${metrics.awayProxyPpda}',
            badgeColor: metrics.homeProxyPpda == 'HIGH'
                ? Colors.redAccent
                : Colors.amberAccent,
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: _buildMetricTile(
            label: 'PA進入 (左/中/右)',
            value:
                '${metrics.paEntryLeft} / ${metrics.paEntryCenter} / ${metrics.paEntryRight}',
            badgeColor: Colors.tealAccent,
          ),
        ),
      ],
    );
  }

  Widget _buildMetricTile({
    required String label,
    required String value,
    required Color badgeColor,
  }) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: Colors.black38,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: Colors.white12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(color: Colors.white54, fontSize: 9),
          ),
          const SizedBox(height: 1),
          Text(
            value,
            style: TextStyle(
              color: badgeColor,
              fontSize: 10.5,
              fontWeight: FontWeight.bold,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildShotQualityRow() {
    return Row(
      children: [
        const Text(
          '1シュートあたり決定機品質: ',
          style: TextStyle(color: Colors.white54, fontSize: 9.5),
        ),
        Row(
          children: List.generate(5, (index) {
            return Icon(
              Icons.star,
              size: 13,
              color: index < metrics.shotQualityStars
                  ? Colors.amber
                  : Colors.white24,
            );
          }),
        ),
      ],
    );
  }
}
