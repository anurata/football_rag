import 'package:flutter/material.dart';

import '../../models/live_match_models.dart';

/// 上部通知バナー: 警戒時間帯到達やAIつぶやき発生時にスライドイン
class LiveAlertBanner extends StatelessWidget {
  final TimelineAlert? alert;
  final VoidCallback? onTap;
  final VoidCallback? onClose;

  const LiveAlertBanner({
    super.key,
    this.alert,
    this.onTap,
    this.onClose,
  });

  @override
  Widget build(BuildContext context) {
    final a = alert;
    if (a == null || !a.active) {
      return const SizedBox.shrink();
    }

    return Container(
      margin: const EdgeInsets.only(bottom: 6),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: const Color(0xFF7F1D1D), // Deep warning red
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: Colors.redAccent.withValues(alpha: 0.6)),
        boxShadow: [
          BoxShadow(
            color: Colors.red.withValues(alpha: 0.3),
            blurRadius: 6,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Row(
        children: [
          const Icon(Icons.warning_amber_rounded,
              color: Colors.amberAccent, size: 14),
          const SizedBox(width: 6),
          Expanded(
            child: GestureDetector(
              onTap: onTap,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    a.title,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 10,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  Text(
                    a.message,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: Colors.white70,
                      fontSize: 9,
                    ),
                  ),
                ],
              ),
            ),
          ),
          if (onClose != null)
            GestureDetector(
              onTap: onClose,
              child: const Padding(
                padding: EdgeInsets.only(left: 6),
                child: Icon(Icons.close, size: 12, color: Colors.white60),
              ),
            ),
        ],
      ),
    );
  }
}
