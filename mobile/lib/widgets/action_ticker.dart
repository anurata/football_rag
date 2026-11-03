import 'package:flutter/material.dart';
import '../models/action_models.dart';

class ActionTicker extends StatelessWidget {
  final int currentMinute;
  final List<UserAction> recentActions;
  final String syncStatus;
  final VoidCallback onIncrementMinute;
  final VoidCallback onDecrementMinute;
  final Function(UserAction action)? onTapAction;
  final Function(UserAction action)? onLongPressAction;

  const ActionTicker({
    super.key,
    required this.currentMinute,
    required this.recentActions,
    required this.syncStatus,
    required this.onIncrementMinute,
    required this.onDecrementMinute,
    this.onTapAction,
    this.onLongPressAction,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: Colors.grey[900],
        boxShadow: const [
          BoxShadow(
            color: Colors.black45,
            blurRadius: 6,
            offset: Offset(0, -2),
          ),
        ],
      ),
      child: SafeArea(
        top: false,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            _buildControlBar(),
            const SizedBox(height: 6),
            _buildActionList(),
          ],
        ),
      ),
    );
  }

  Widget _buildControlBar() {
    final isOnline = syncStatus.contains('Online') || syncStatus.contains('Synced');

    return Row(
      children: [
        // Match minute controller
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
          decoration: BoxDecoration(
            color: Colors.black,
            borderRadius: BorderRadius.circular(6),
            border: Border.all(color: Colors.white24),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              IconButton(
                visualDensity: VisualDensity.compact,
                iconSize: 16,
                padding: EdgeInsets.zero,
                constraints: const BoxConstraints(),
                icon: const Icon(Icons.remove, color: Colors.white70),
                onPressed: onDecrementMinute,
              ),
              const SizedBox(width: 6),
              Text(
                "$currentMinute'",
                style: const TextStyle(
                  color: Colors.amber,
                  fontWeight: FontWeight.bold,
                  fontSize: 15,
                ),
              ),
              const SizedBox(width: 6),
              IconButton(
                visualDensity: VisualDensity.compact,
                iconSize: 16,
                padding: EdgeInsets.zero,
                constraints: const BoxConstraints(),
                icon: const Icon(Icons.add, color: Colors.white70),
                onPressed: onIncrementMinute,
              ),
            ],
          ),
        ),
        const SizedBox(width: 8),

        // Sync status pill
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
          decoration: BoxDecoration(
            color: isOnline ? Colors.green[900] : Colors.orange[900],
            borderRadius: BorderRadius.circular(12),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                isOnline ? Icons.cloud_done : Icons.cloud_queue,
                size: 12,
                color: Colors.white,
              ),
              const SizedBox(width: 4),
              Text(
                syncStatus,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 10,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
        ),
        const Spacer(),
        Text(
          'Total: ${recentActions.length}',
          style: const TextStyle(color: Colors.white54, fontSize: 11),
        ),
      ],
    );
  }

  Widget _buildActionList() {
    if (recentActions.isEmpty) {
      return const SizedBox(
        height: 30,
        child: Center(
          child: Text(
            '選手ピンを上スワイプでGood👍 / 下スワイプでBad👎',
            style: TextStyle(color: Colors.white38, fontSize: 11),
          ),
        ),
      );
    }

    return SizedBox(
      height: 30,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: recentActions.length,
        separatorBuilder: (context, index) => const SizedBox(width: 6),
        itemBuilder: (context, index) {
          final act = recentActions[index];
          return _buildActionChip(act);
        },
      ),
    );
  }

  Widget _buildActionChip(UserAction act) {
    final isGood = act.actionType == 'good';
    final hasBonus = act.bonusPoints > 0;

    return GestureDetector(
      onTap: () {
        if (onTapAction != null) {
          onTapAction!(act);
        }
      },
      onLongPress: () {
        if (onLongPressAction != null) {
          onLongPressAction!(act);
        }
      },
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
        decoration: BoxDecoration(
          color: isGood ? Colors.green[800] : Colors.red[800],
          borderRadius: BorderRadius.circular(12),
          border: hasBonus
              ? Border.all(color: Colors.amber, width: 1.2)
              : null,
          boxShadow: hasBonus
              ? const [
                  BoxShadow(
                    color: Colors.amberAccent,
                    blurRadius: 4,
                    offset: Offset(0, 1),
                  ),
                ]
              : null,
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              "${act.matchMinute}'",
              style: const TextStyle(
                fontSize: 10,
                fontWeight: FontWeight.bold,
                color: Colors.white70,
              ),
            ),
            const SizedBox(width: 4),
            Text(
              act.playerName ?? act.playerId,
              style: const TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.bold,
                color: Colors.white,
              ),
            ),
            const SizedBox(width: 4),
            Icon(
              isGood ? Icons.thumb_up : Icons.thumb_down,
              size: 11,
              color: Colors.white,
            ),
            if (hasBonus) ...[
              const SizedBox(width: 3),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 3, vertical: 0.5),
                decoration: BoxDecoration(
                  color: Colors.amber,
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text(
                  '+${act.bonusPoints}',
                  style: const TextStyle(
                    fontSize: 9,
                    fontWeight: FontWeight.bold,
                    color: Colors.black,
                  ),
                ),
              ),
            ],
            if (act.playCategory != null) ...[
              const SizedBox(width: 3),
              Text(
                '(${act.playCategory})',
                style: const TextStyle(fontSize: 9, color: Colors.white70),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
