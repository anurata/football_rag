import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../models/action_models.dart';

class ActionTicker extends StatelessWidget {
  final int currentMinute;
  final String formattedTime;
  final bool isTimerRunning;
  final bool isOver45Minutes;
  final List<UserAction> recentActions;
  final String syncStatus;
  final VoidCallback onIncrementMinute;
  final VoidCallback onDecrementMinute;
  final VoidCallback? onToggleTimer;
  final VoidCallback? onLongPressTimer;
  final Function(UserAction action)? onTapAction;
  final Function(UserAction action)? onLongPressAction;

  const ActionTicker({
    super.key,
    required this.currentMinute,
    this.formattedTime = '00:00',
    this.isTimerRunning = false,
    this.isOver45Minutes = false,
    required this.recentActions,
    required this.syncStatus,
    required this.onIncrementMinute,
    required this.onDecrementMinute,
    this.onToggleTimer,
    this.onLongPressTimer,
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
        _buildStopwatchBox(),
        const SizedBox(width: 8),
        _buildSyncPill(isOnline),
        const Spacer(),
        _buildTotalCount(),
      ],
    );
  }

  Widget _buildStopwatchBox() {
    // Orange background when exceeding 45 minutes
    final bgColor = isOver45Minutes ? const Color(0xFFEA580C) : Colors.black;
    final borderColor = isOver45Minutes ? Colors.amber : Colors.white24;

    return GestureDetector(
      onLongPress: () {
        HapticFeedback.heavyImpact();
        if (onLongPressTimer != null) onLongPressTimer!();
      },
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
        decoration: BoxDecoration(
          color: bgColor,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: borderColor, width: 1.2),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            // Decrement minute button (only when paused)
            if (!isTimerRunning) ...[
              IconButton(
                visualDensity: VisualDensity.compact,
                iconSize: 16,
                padding: EdgeInsets.zero,
                constraints: const BoxConstraints(),
                icon: const Icon(Icons.remove, color: Colors.white70),
                onPressed: () {
                  HapticFeedback.selectionClick();
                  onDecrementMinute();
                },
              ),
              const SizedBox(width: 4),
            ],

            // Stopwatch time display & play/pause toggle
            GestureDetector(
              onTap: () {
                HapticFeedback.selectionClick();
                if (onToggleTimer != null) onToggleTimer!();
              },
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    isTimerRunning ? Icons.pause : Icons.play_arrow,
                    size: 14,
                    color: Colors.white,
                  ),
                  const SizedBox(width: 4),
                  Text(
                    formattedTime,
                    style: const TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.bold,
                      fontSize: 14,
                      letterSpacing: 0.5,
                      fontFeatures: [FontFeature.tabularFigures()],
                    ),
                  ),
                ],
              ),
            ),

            // Increment minute button (only when paused)
            if (!isTimerRunning) ...[
              const SizedBox(width: 4),
              IconButton(
                visualDensity: VisualDensity.compact,
                iconSize: 16,
                padding: EdgeInsets.zero,
                constraints: const BoxConstraints(),
                icon: const Icon(Icons.add, color: Colors.white70),
                onPressed: () {
                  HapticFeedback.selectionClick();
                  onIncrementMinute();
                },
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildSyncPill(bool isOnline) {
    return Container(
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
    );
  }

  Widget _buildTotalCount() {
    return Text(
      'Total: ${recentActions.length}',
      style: const TextStyle(color: Colors.white54, fontSize: 11),
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
