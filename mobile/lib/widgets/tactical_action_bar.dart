import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// Slim tactical toolbar placed above the bench tray for substitutions,
/// position swapping, and in-match player rating rankings.
class TacticalActionBar extends StatelessWidget {
  final VoidCallback onSubstituteTap;
  final VoidCallback onSwapPositionsTap;
  final VoidCallback onShowRankingsTap;

  const TacticalActionBar({
    super.key,
    required this.onSubstituteTap,
    required this.onSwapPositionsTap,
    required this.onShowRankingsTap,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 32,
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
      decoration: const BoxDecoration(
        color: Color(0xFF0F172A), // Slate 900
        border: Border(
          bottom: BorderSide(
            color: Colors.white12,
            width: 1,
          ),
        ),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          _buildBarButton(
            icon: Icons.swap_horiz,
            label: '選手交代',
            color: Colors.amberAccent,
            onTap: onSubstituteTap,
          ),
          const VerticalDivider(
            color: Colors.white24,
            indent: 4,
            endIndent: 4,
            width: 1,
          ),
          _buildBarButton(
            icon: Icons.sync_alt,
            label: '位置入替',
            color: Colors.cyanAccent,
            onTap: onSwapPositionsTap,
          ),
          const VerticalDivider(
            color: Colors.white24,
            indent: 4,
            endIndent: 4,
            width: 1,
          ),
          _buildBarButton(
            icon: Icons.leaderboard,
            label: '評価ランク',
            color: Colors.lightGreenAccent,
            onTap: onShowRankingsTap,
          ),
        ],
      ),
    );
  }

  Widget _buildBarButton({
    required IconData icon,
    required String label,
    required Color color,
    required VoidCallback onTap,
  }) {
    return InkWell(
      onTap: () {
        HapticFeedback.mediumImpact();
        onTap();
      },
      borderRadius: BorderRadius.circular(4),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              icon,
              size: 13,
              color: color,
            ),
            const SizedBox(width: 4),
            Text(
              label,
              style: TextStyle(
                fontSize: 10,
                fontWeight: FontWeight.w600,
                color: color,
                letterSpacing: 0.2,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
