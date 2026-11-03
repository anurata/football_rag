import 'package:flutter/material.dart';
import '../models/match_models.dart';
import 'player_pin.dart';

class PitchBoard extends StatelessWidget {
  final TeamContextItem team;
  final Function(PlayerContextItem player, String actionType, String? category) onPlayerAction;

  const PitchBoard({
    super.key,
    required this.team,
    required this.onPlayerAction,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        if (team.bench.isNotEmpty) _buildBenchTray(context),
        Expanded(
          child: LayoutBuilder(
            builder: (context, constraints) {
              return Stack(
                children: [
                  Positioned.fill(
                    child: CustomPaint(
                      painter: _SoccerPitchPainter(),
                    ),
                  ),
                  ...team.starters.map((player) {
                    return _buildPositionedPlayer(player, constraints);
                  }),
                ],
              );
            },
          ),
        ),
      ],
    );
  }

  Widget _buildBenchTray(BuildContext context) {
    return Container(
      height: 48,
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      color: Colors.black87,
      child: Row(
        children: [
          const Text(
            'BENCH:',
            style: TextStyle(
              fontSize: 10,
              fontWeight: FontWeight.bold,
              color: Colors.amber,
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              itemCount: team.bench.length,
              separatorBuilder: (context, index) => const SizedBox(width: 6),
              itemBuilder: (context, index) {
                final p = team.bench[index];
                return ActionChip(
                  padding: EdgeInsets.zero,
                  label: Text('#${p.number} ${p.playerName}'),
                  labelStyle: const TextStyle(fontSize: 10, color: Colors.white),
                  backgroundColor: Colors.white24,
                  onPressed: () => onPlayerAction(p, 'good', null),
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildPositionedPlayer(
    PlayerContextItem player,
    BoxConstraints constraints,
  ) {
    // pitchX and pitchY are in 0.0 - 100.0 range
    final posX = (player.pitchX / 100.0) * constraints.maxWidth;
    final posY = (player.pitchY / 100.0) * constraints.maxHeight;

    // Pin size optimized to prevent text overflows while preserving pitch space
    const pinW = 82.0;
    const pinH = 46.0;

    final left = (posX - (pinW / 2)).clamp(4.0, constraints.maxWidth - pinW - 4.0);
    final top = (posY - (pinH / 2)).clamp(4.0, constraints.maxHeight - pinH - 4.0);

    return Positioned(
      left: left,
      top: top,
      width: pinW,
      height: pinH,
      child: PlayerPin(
        player: player,
        teamId: team.teamId,
        onAction: (actionType, category) {
          onPlayerAction(player, actionType, category);
        },
      ),
    );
  }
}

class _SoccerPitchPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    // 1. Grass background gradient
    final grassPaint = Paint()
      ..shader = const LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: [
          Color(0xFF1B5E20),
          Color(0xFF2E7D32),
          Color(0xFF1B5E20),
        ],
      ).createShader(Rect.fromLTWH(0, 0, size.width, size.height));
    canvas.drawRect(Rect.fromLTWH(0, 0, size.width, size.height), grassPaint);

    // 2. White pitch lines
    final linePaint = Paint()
      ..color = Colors.white.withValues(alpha: 0.6)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.0;

    // Outer border
    canvas.drawRect(
      Rect.fromLTWH(8, 8, size.width - 16, size.height - 16),
      linePaint,
    );

    // Halfway line
    final midY = size.height / 2;
    canvas.drawLine(
      Offset(8, midY),
      Offset(size.width - 8, midY),
      linePaint,
    );

    // Center circle
    final center = Offset(size.width / 2, midY);
    canvas.drawCircle(center, size.width * 0.16, linePaint);
    canvas.drawCircle(center, 3.0, Paint()..color = Colors.white70);

    // Penalty areas
    _drawPenaltyArea(canvas, size, linePaint, isTop: true);
    _drawPenaltyArea(canvas, size, linePaint, isTop: false);
  }

  void _drawPenaltyArea(
    Canvas canvas,
    Size size,
    Paint paint, {
    required bool isTop,
  }) {
    final boxW = size.width * 0.55;
    final boxH = size.height * 0.14;
    final left = (size.width - boxW) / 2;
    final top = isTop ? 8.0 : (size.height - 8.0 - boxH);

    canvas.drawRect(Rect.fromLTWH(left, top, boxW, boxH), paint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
