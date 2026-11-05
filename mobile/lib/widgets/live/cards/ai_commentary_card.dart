import 'package:flutter/material.dart';

import '../../../models/live_match_models.dart';

/// カード⑤: AI解説 ✕ つぶやきタイムライン (Ear-First 音声ボタン付き)
class AiCommentaryCard extends StatelessWidget {
  final AiTweetItem? tweet;
  final bool isSpeaking;
  final VoidCallback? onSpeakTap;
  final VoidCallback? onAskLlmTap;

  const AiCommentaryCard({
    super.key,
    this.tweet,
    this.isSpeaking = false,
    this.onSpeakTap,
    this.onAskLlmTap,
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
          _buildTweetBubble(),
          _buildBottomActionButtons(),
        ],
      ),
    );
  }

  Widget _buildHeaderRow() {
    final speaker = tweet?.speakerName ?? '裏実況・AIサッカー仲間';
    final time = tweet?.timestamp ?? "65'";

    return Row(
      children: [
        const Icon(Icons.forum_outlined, color: Colors.purpleAccent, size: 14),
        const SizedBox(width: 6),
        Text(
          speaker,
          style: const TextStyle(
            color: Colors.purpleAccent,
            fontSize: 11,
            fontWeight: FontWeight.bold,
          ),
        ),
        const Spacer(),
        Text(
          '$time つぶやき',
          style: const TextStyle(color: Colors.white38, fontSize: 9.5),
        ),
      ],
    );
  }

  Widget _buildTweetBubble() {
    final text = tweet?.text ??
        '相手が後半からブロックを下げてきたね。サイドチェンジで揺さぶりをかけたいところ…！';

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: Colors.purple.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.purpleAccent.withValues(alpha: 0.3)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('💬 ', style: TextStyle(fontSize: 11)),
          Expanded(
            child: Text(
              text,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 10.5,
                height: 1.25,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildBottomActionButtons() {
    return Row(
      children: [
        InkWell(
          onTap: onSpeakTap,
          borderRadius: BorderRadius.circular(4),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
            decoration: BoxDecoration(
              color: isSpeaking
                  ? Colors.redAccent.withValues(alpha: 0.3)
                  : Colors.white10,
              borderRadius: BorderRadius.circular(4),
              border: Border.all(
                color: isSpeaking ? Colors.redAccent : Colors.white24,
              ),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  isSpeaking ? Icons.volume_up : Icons.volume_down_outlined,
                  size: 13,
                  color: isSpeaking ? Colors.redAccent : Colors.white70,
                ),
                const SizedBox(width: 4),
                Text(
                  isSpeaking ? '読上中...' : '音声を聞く',
                  style: TextStyle(
                    color: isSpeaking ? Colors.redAccent : Colors.white70,
                    fontSize: 9.5,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ],
            ),
          ),
        ),
        const Spacer(),
        InkWell(
          onTap: onAskLlmTap,
          borderRadius: BorderRadius.circular(4),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
            decoration: BoxDecoration(
              color: Colors.amber.withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(4),
              border: Border.all(
                color: Colors.amber.withValues(alpha: 0.3),
              ),
            ),
            child: const Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.psychology, size: 13, color: Colors.amber),
                SizedBox(width: 4),
                Text(
                  '「なぜ？」と質問',
                  style: TextStyle(
                    color: Colors.amber,
                    fontSize: 9.5,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}
