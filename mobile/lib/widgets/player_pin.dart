import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/match_models.dart';

class PlayerPin extends StatefulWidget {
  final PlayerContextItem player;
  final String teamId;
  final Function(String actionType, String? category) onAction;

  const PlayerPin({
    super.key,
    required this.player,
    required this.teamId,
    required this.onAction,
  });

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
      // Swiped Up: Good!
      HapticFeedback.mediumImpact();
      _triggerFlash(Colors.green.withValues(alpha: 0.6));
      widget.onAction('good', null);
    } else if (vy > 150) {
      // Swiped Down: Bad!
      HapticFeedback.heavyImpact();
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
        padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
        decoration: _buildBoxDecoration(),
        child: Center(
          child: FittedBox(
            fit: BoxFit.scaleDown,
            child: _buildPinContent(),
          ),
        ),
      ),
    );
  }

  BoxDecoration _buildBoxDecoration() {
    final isFlashing = _flashColor != Colors.transparent;
    return BoxDecoration(
      color: isFlashing ? _flashColor : Colors.black.withValues(alpha: 0.75),
      borderRadius: BorderRadius.circular(14),
      border: Border.all(
        color: isFlashing ? Colors.white : Colors.white70,
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

  Widget _buildPinContent() {
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        _buildNumberAndPositionRow(),
        const SizedBox(height: 2),
        _buildPlayerNameText(),
      ],
    );
  }

  Widget _buildNumberAndPositionRow() {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        _buildNumberBadge(),
        const SizedBox(width: 4),
        _buildPositionLabel(),
      ],
    );
  }

  Widget _buildNumberBadge() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 3, vertical: 1),
      decoration: BoxDecoration(
        color: Colors.amber,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(
        '${widget.player.number}',
        style: const TextStyle(
          fontSize: 10,
          fontWeight: FontWeight.bold,
          color: Colors.black,
        ),
      ),
    );
  }

  Widget _buildPositionLabel() {
    return Text(
      widget.player.position,
      style: const TextStyle(
        fontSize: 9,
        fontWeight: FontWeight.bold,
        color: Colors.white70,
      ),
    );
  }

  Widget _buildPlayerNameText() {
    return Text(
      widget.player.playerName,
      style: const TextStyle(
        fontSize: 10,
        fontWeight: FontWeight.w600,
        color: Colors.white,
      ),
      overflow: TextOverflow.ellipsis,
      maxLines: 1,
      textAlign: TextAlign.center,
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
