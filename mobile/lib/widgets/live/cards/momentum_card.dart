import 'package:flutter/material.dart';

import '../../../models/action_models.dart';

/// カード③: モメンタム波形 ✕ Good/Badログ重ね合わせカード
class MomentumCard extends StatelessWidget {
  final List<UserAction> actions;
  final int currentMinute;

  const MomentumCard({
    super.key,
    required this.actions,
    this.currentMinute = 65,
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
          _buildWaveformGraph(),
          _buildLegendRow(),
        ],
      ),
    );
  }

  Widget _buildHeaderRow() {
    return const Row(
      children: [
        Icon(Icons.show_chart, color: Colors.amberAccent, size: 14),
        SizedBox(width: 6),
        Text(
          '試合モメンタム ✕ 感情ログ同期',
          style: TextStyle(
            color: Colors.amberAccent,
            fontSize: 11,
            fontWeight: FontWeight.bold,
          ),
        ),
        Spacer(),
        Text(
          'あなたの眼力とデータのシンクロ',
          style: TextStyle(color: Colors.white38, fontSize: 9.5),
        ),
      ],
    );
  }

  Widget _buildWaveformGraph() {
    return Container(
      height: 52,
      width: double.infinity,
      decoration: BoxDecoration(
        color: Colors.black26,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: Colors.white12),
      ),
      child: CustomPaint(
        painter: _MomentumPainter(
          actions: actions,
          currentMinute: currentMinute,
        ),
      ),
    );
  }

  Widget _buildLegendRow() {
    final goodCount = actions.where((a) => a.actionType == 'good').length;
    final badCount = actions.where((a) => a.actionType == 'bad').length;

    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Row(
          children: [
            Container(
              width: 8,
              height: 8,
              decoration: const BoxDecoration(
                color: Colors.greenAccent,
                shape: BoxShape.circle,
              ),
            ),
            const SizedBox(width: 4),
            Text(
              'Good ($goodCount件)',
              style: const TextStyle(color: Colors.white70, fontSize: 10),
            ),
            const SizedBox(width: 10),
            Container(
              width: 8,
              height: 8,
              decoration: const BoxDecoration(
                color: Colors.redAccent,
                shape: BoxShape.circle,
              ),
            ),
            const SizedBox(width: 4),
            Text(
              'Bad ($badCount件)',
              style: const TextStyle(color: Colors.white70, fontSize: 10),
            ),
          ],
        ),
        Text(
          '現在 $currentMinute 分',
          style: const TextStyle(
            color: Colors.amber,
            fontSize: 10,
            fontWeight: FontWeight.bold,
          ),
        ),
      ],
    );
  }
}

class _MomentumPainter extends CustomPainter {
  final List<UserAction> actions;
  final int currentMinute;

  _MomentumPainter({
    required this.actions,
    required this.currentMinute,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final midY = size.height / 2;

    // 1. Center base line
    final basePaint = Paint()
      ..color = Colors.white12
      ..strokeWidth = 1.0;
    canvas.drawLine(Offset(0, midY), Offset(size.width, midY), basePaint);

    // 2. Simulated Momentum Wave (0 - 90 min)
    final wavePaint = Paint()
      ..color = Colors.cyanAccent.withValues(alpha: 0.6)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.8;

    final path = Path();
    const totalMin = 90.0;
    final maxPts = (currentMinute.clamp(1, 90) * (size.width / totalMin));

    for (double x = 0; x <= maxPts; x += 4.0) {
      final m = (x / size.width) * totalMin;
      // Multi-sine wave simulation
      final yOffset =
          (14.0 * (0.6 * (m * 0.15).abs() % 1.0 - 0.5)) +
          (6.0 * (m % 10 > 5 ? 1 : -1));
      final y = midY + yOffset.clamp(-size.height * 0.4, size.height * 0.4);

      if (x == 0) {
        path.moveTo(x, y);
      } else {
        path.lineTo(x, y);
      }
    }
    canvas.drawPath(path, wavePaint);

    // 3. User Good / Bad action pins overlaid
    for (final a in actions) {
      final actMin = a.matchMinute.clamp(0, 90);
      final x = (actMin / totalMin) * size.width;
      final isGood = a.actionType == 'good';

      final dotPaint = Paint()
        ..color = isGood ? Colors.greenAccent : Colors.redAccent
        ..style = PaintingStyle.fill;

      final y = isGood ? midY - 14.0 : midY + 14.0;
      canvas.drawCircle(Offset(x, y), 2.8, dotPaint);
    }
  }

  @override
  bool shouldRepaint(covariant _MomentumPainter oldDelegate) {
    return oldDelegate.actions.length != actions.length ||
        oldDelegate.currentMinute != currentMinute;
  }
}
