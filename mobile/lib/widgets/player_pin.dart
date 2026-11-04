import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/match_models.dart';

class PlayerPin extends StatefulWidget {
  final PlayerContextItem player;
  final String teamId;
  final bool isHome;
  final int score;
  final Function(String actionType, String? category) onAction;

  const PlayerPin({
    super.key,
    required this.player,
    required this.teamId,
    this.isHome = true,
    this.score = 0,
    required this.onAction,
  });

  static Color calculateScoreBadgeColor(int score, {bool isHome = true}) {
    // Clamped strictly between -5 (lower limit) and +15 (upper limit)
    final clamped = score.clamp(-5, 15);
    const neutralColor = Colors.white; // 0 pts initial: clean white
    const minBlue = Color(0xFF1D4ED8); // -5 pts lower limit: deep cobalt blue
    const midRed = Color(0xFFE11D48); // +7 pts: rich crimson red
    const maxGold = Color(0xFFFFD700); // +15 pts upper limit: shining gold

    if (clamped == 0) {
      return neutralColor;
    } else if (clamped < 0) {
      // 1-step per point gradient from 0 down to -5 (White -> Deep Blue)
      final t = clamped.abs() / 5.0;
      return Color.lerp(neutralColor, minBlue, t)!;
    } else {
      // 0 to +7: White -> Crimson Red gradient
      if (clamped <= 7) {
        final t = clamped / 7.0;
        return Color.lerp(neutralColor, midRed, t)!;
      } else {
        // +7 to +15: Crimson Red -> Shining Gold gradient
        final t = (clamped - 7) / 8.0;
        return Color.lerp(midRed, maxGold, t)!;
      }
    }
  }

  @override
  State<PlayerPin> createState() => _PlayerPinState();
}

class _PlayerPinState extends State<PlayerPin> {
  Color _flashColor = Colors.transparent;

  void _triggerFlash(Color color) {
    setState(() {
      _flashColor = color;
    });
    Future.delayed(const Duration(milliseconds: 300), () {
      if (mounted) {
        setState(() {
          _flashColor = Colors.transparent;
        });
      }
    });
  }

  void _handleVerticalDrag(DragEndDetails details) {
    final vy = details.primaryVelocity ?? 0;
    if (vy < -150) {
      // Swiped Up: Good! (Strong medium impact haptic)
      HapticFeedback.mediumImpact();
      _triggerFlash(Colors.green.withValues(alpha: 0.6));
      widget.onAction('good', null);
    } else if (vy > 150) {
      // Swiped Down: Bad! (Strong medium impact haptic)
      HapticFeedback.mediumImpact();
      _triggerFlash(Colors.red.withValues(alpha: 0.6));
      widget.onAction('bad', null);
    }
  }

  void _showCategoryDialog(BuildContext context) {
    showModalBottomSheet(
      context: context,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) {
        return _CategorySelectSheet(
          playerName: widget.player.playerName,
          number: widget.player.number,
          onSelect: (type, cat) {
            Navigator.pop(ctx);
            HapticFeedback.mediumImpact();
            _triggerFlash(
              type == 'good'
                  ? Colors.green.withValues(alpha: 0.6)
                  : Colors.red.withValues(alpha: 0.6),
            );
            widget.onAction(type, cat);
          },
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onVerticalDragEnd: _handleVerticalDrag,
      onTap: () => _showCategoryDialog(context),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.symmetric(horizontal: 3, vertical: 2),
        decoration: _buildBoxDecoration(),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            _buildNumberAndPositionRow(),
            const SizedBox(height: 1),
            Expanded(
              child: _buildPlayerNameText(),
            ),
          ],
        ),
      ),
    );
  }

  BoxDecoration _buildBoxDecoration() {
    final isFlashing = _flashColor != Colors.transparent;
    if (isFlashing) {
      return BoxDecoration(
        color: _flashColor,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.white, width: 1.5),
        boxShadow: const [
          BoxShadow(
            color: Colors.black45,
            blurRadius: 4,
            offset: Offset(0, 2),
          ),
        ],
      );
    }

    // Home: Club color (Fagiano Red 0xFF7D1B2D) with subtle border
    // Away: Crisp white kit (0xFFFFFFFF) with club navy border
    if (widget.isHome) {
      return BoxDecoration(
        color: const Color(0xFF7D1B2D),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: Colors.white.withValues(alpha: 0.85),
          width: 1.2,
        ),
        boxShadow: const [
          BoxShadow(
            color: Colors.black54,
            blurRadius: 4,
            offset: Offset(0, 2),
          ),
        ],
      );
    } else {
      return BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: const Color(0xFF1E3A8A),
          width: 1.5,
        ),
        boxShadow: const [
          BoxShadow(
            color: Colors.black38,
            blurRadius: 4,
            offset: Offset(0, 2),
          ),
        ],
      );
    }
  }

  Widget _buildNumberAndPositionRow() {
    return Row(
      mainAxisSize: MainAxisSize.min,
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        _buildNumberBadge(),
        const SizedBox(width: 3),
        _buildPositionLabel(),
        _buildScorePill(),
      ],
    );
  }

  Widget _buildNumberBadge() {
    final badgeBg =
        PlayerPin.calculateScoreBadgeColor(widget.score, isHome: widget.isHome);
    final badgeTextColor = _calculateBadgeTextColor(badgeBg);

    return Container(
      width: 18,
      height: 18,
      decoration: BoxDecoration(
        color: badgeBg,
        shape: BoxShape.circle,
        border: widget.score >= 10
            ? Border.all(color: const Color(0xFFFFD700), width: 1.2)
            : Border.all(color: Colors.black26, width: 0.8),
      ),
      alignment: Alignment.center,
      child: Text(
        '${widget.player.number}',
        textScaler: TextScaler.noScaling,
        style: TextStyle(
          fontSize: 9.5,
          fontWeight: FontWeight.bold,
          color: badgeTextColor,
          height: 1.1,
        ),
      ),
    );
  }

  Color _calculateBadgeTextColor(Color bg) {
    return bg.computeLuminance() > 0.45 ? Colors.black : Colors.white;
  }

  Widget _buildScorePill() {
    if (widget.score == 0) return const SizedBox.shrink();
    final isPos = widget.score > 0;
    final prefix = isPos ? '+' : '';
    final pillColor = isPos ? const Color(0xFF16A34A) : const Color(0xFFDC2626);

    return Container(
      margin: const EdgeInsets.only(left: 3),
      padding: const EdgeInsets.symmetric(horizontal: 2.5, vertical: 0.5),
      decoration: BoxDecoration(
        color: pillColor,
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(
        '$prefix${widget.score}',
        textScaler: TextScaler.noScaling,
        style: const TextStyle(
          fontSize: 8.0,
          fontWeight: FontWeight.bold,
          color: Colors.white,
        ),
      ),
    );
  }

  Widget _buildPositionLabel() {
    final textColor = widget.isHome
        ? Colors.white.withValues(alpha: 0.9)
        : const Color(0xFF334155);

    return Text(
      widget.player.position,
      textScaler: TextScaler.noScaling,
      style: TextStyle(
        fontSize: 9.0,
        fontWeight: FontWeight.bold,
        color: textColor,
      ),
    );
  }

  Widget _buildPlayerNameText() {
    final textColor = widget.isHome ? Colors.white : const Color(0xFF0F172A);

    return SizedBox(
      width: double.infinity,
      child: FittedBox(
        fit: BoxFit.scaleDown,
        child: Text(
          widget.player.displayName,
          style: TextStyle(
            fontSize: 9.5,
            fontWeight: FontWeight.bold,
            color: textColor,
          ),
          maxLines: 1,
          textAlign: TextAlign.center,
        ),
      ),
    );
  }
}

class _CategorySelectSheet extends StatelessWidget {
  final String playerName;
  final int number;
  final Function(String actionType, String category) onSelect;

  const _CategorySelectSheet({
    required this.playerName,
    required this.number,
    required this.onSelect,
  });

  @override
  Widget build(BuildContext context) {
    final categories = ['パス', '守備/プレス', 'シュート', 'デュエル', 'ドリブル', 'クロス'];

    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              '#$number $playerName のプレー評価',
              style: const TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.bold,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 16),
            const Text(
              '👍 ナイスプレー (Good)',
              style: TextStyle(
                fontWeight: FontWeight.bold,
                color: Colors.green,
              ),
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              children: categories.map((cat) {
                return ActionChip(
                  avatar: const Icon(Icons.thumb_up, size: 14, color: Colors.green),
                  label: Text(cat),
                  onPressed: () => onSelect('good', cat),
                );
              }).toList(),
            ),
            const SizedBox(height: 16),
            const Text(
              '👎 課題・ミス (Bad)',
              style: TextStyle(
                fontWeight: FontWeight.bold,
                color: Colors.redAccent,
              ),
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              children: categories.map((cat) {
                return ActionChip(
                  avatar: const Icon(Icons.thumb_down, size: 14, color: Colors.redAccent),
                  label: Text(cat),
                  onPressed: () => onSelect('bad', cat),
                );
              }).toList(),
            ),
          ],
        ),
      ),
    );
  }
}
