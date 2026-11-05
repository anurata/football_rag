import 'package:flutter/material.dart';

import '../../../models/live_match_models.dart';

/// カード⑥: 速報生リスト (時系列テキストログ)
class LiveRawListCard extends StatelessWidget {
  final List<RawEventItem> events;

  const LiveRawListCard({
    super.key,
    required this.events,
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
        children: [
          _buildHeaderRow(),
          const SizedBox(height: 4),
          Expanded(child: _buildEventList()),
        ],
      ),
    );
  }

  Widget _buildHeaderRow() {
    return const Row(
      children: [
        Icon(Icons.list_alt, color: Colors.blueGrey, size: 14),
        SizedBox(width: 6),
        Text(
          '公式速報・イベント生ログ',
          style: TextStyle(
            color: Colors.white70,
            fontSize: 11,
            fontWeight: FontWeight.bold,
          ),
        ),
        Spacer(),
        Text(
          '時系列タイムライン',
          style: TextStyle(color: Colors.white38, fontSize: 9.5),
        ),
      ],
    );
  }

  Widget _buildEventList() {
    if (events.isEmpty) {
      return const Center(
        child: Text(
          'まだ速報イベントはありません',
          style: TextStyle(color: Colors.white38, fontSize: 10),
        ),
      );
    }

    return ListView.builder(
      itemCount: events.length,
      padding: EdgeInsets.zero,
      itemBuilder: (context, index) {
        final item = events[index];
        return Padding(
          padding: const EdgeInsets.symmetric(vertical: 2.0),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Text(
                item.icon,
                style: const TextStyle(fontSize: 11),
              ),
              const SizedBox(width: 4),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 0.5),
                decoration: BoxDecoration(
                  color: Colors.white12,
                  borderRadius: BorderRadius.circular(2),
                ),
                child: Text(
                  item.time,
                  style: const TextStyle(
                    color: Colors.amberAccent,
                    fontSize: 9,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  '${item.title}: ${item.description}',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: Colors.white70,
                    fontSize: 9.5,
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}
