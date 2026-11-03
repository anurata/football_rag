import 'package:flutter/material.dart';
import '../models/match_models.dart';
import 'player_pin.dart';

class PitchBoard extends StatelessWidget {
  final TeamContextItem team;
  final bool isHome;
  final Map<String, int> playerScores;
  final Function(PlayerContextItem player, String actionType, String? category) onPlayerAction;

  const PitchBoard({
    super.key,
    required this.team,
    this.isHome = true,
    this.playerScores = const {},
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
                final score = playerScores[p.playerId] ?? 0;
                final scoreSuffix = score != 0 ? ' (${score > 0 ? '+' : ''}$score)' : '';
                final chipBg = isHome ? const Color(0xFF7D1B2D) : Colors.white;
                final chipText = isHome ? Colors.white : const Color(0xFF0F172A);
                return ActionChip(
                  padding: EdgeInsets.zero,
                  label: Text('#${p.number} ${p.displayName}$scoreSuffix'),
                  labelStyle: TextStyle(
                    fontSize: 10,
                    fontWeight: FontWeight.bold,
                    color: chipText,
                  ),
                  backgroundColor: chipBg,
                  side: BorderSide(
                    color: isHome ? Colors.white38 : const Color(0xFF1E3A8A),
                    width: 1,
                  ),
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
        isHome: isHome,
        score: playerScores[player.playerId] ?? 0,
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
    _drawGrassBackground(canvas, size);
    _drawHalfCourtLines(canvas, size);
  }

  void _drawGrassBackground(Canvas canvas, Size size) {
    final grassPaint = Paint()
      ..shader = const LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: [
          Color(0xFF1B5E20),
          Color(0xFF2E7D32),
          Color(0xFF1E6E26),
        ],
      ).createShader(Rect.fromLTWH(0, 0, size.width, size.height));
    canvas.drawRect(Rect.fromLTWH(0, 0, size.width, size.height), grassPaint);
  }

  void _drawHalfCourtLines(Canvas canvas, Size size) {
    final linePaint = Paint()
      ..color = Colors.white.withValues(alpha: 0.65)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.0;

    const pad = 6.0;
    final w = size.width;
    final h = size.height;

    // 1. Outer half-court border
    canvas.drawRect(
      Rect.fromLTWH(pad, pad, w - (pad * 2), h - (pad * 2)),
      linePaint,
    );

    // 2. Top Halfway Line & Center Circle Arc
    final centerTop = Offset(w / 2, pad);
    canvas.drawArc(
      Rect.fromCircle(center: centerTop, radius: w * 0.20),
      0,
      3.14159265,
      false,
      linePaint,
    );
    canvas.drawCircle(
      centerTop,
      3.0,
      Paint()..color = Colors.white70,
    );

    // 3. Bottom Penalty Area (Large box)
    final penW = w * 0.60;
    final penH = h * 0.28;
    final penLeft = (w - penW) / 2;
    final penTop = h - pad - penH;
    canvas.drawRect(
      Rect.fromLTWH(penLeft, penTop, penW, penH),
      linePaint,
    );

    // 4. Goal Area (Small box)
    final goalW = w * 0.32;
    final goalH = h * 0.12;
    final goalLeft = (w - goalW) / 2;
    final goalTop = h - pad - goalH;
    canvas.drawRect(
      Rect.fromLTWH(goalLeft, goalTop, goalW, goalH),
      linePaint,
    );

    // 5. Penalty Spot (PK dot)
    final pkY = h - pad - (penH * 0.65);
    canvas.drawCircle(
      Offset(w / 2, pkY),
      2.5,
      Paint()..color = Colors.white70,
    );
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
