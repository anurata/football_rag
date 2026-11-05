/// スナップショット全体のデータモデル
class LiveSnapshotData {
  final String matchId;
  final String status;
  final int elapsedMinute;
  final String formattedTime;
  final ScoreBoard score;
  final WinProbability winProb;
  final TeamLiveMetrics metrics;
  final Map<String, PlayerLiveStatusItem> playerLiveStatus;
  final TimelineAlert? timelineAlert;
  final AiTweetItem? latestAiTweet;
  final List<RawEventItem> rawEvents;

  const LiveSnapshotData({
    required this.matchId,
    required this.status,
    required this.elapsedMinute,
    required this.formattedTime,
    required this.score,
    required this.winProb,
    required this.metrics,
    required this.playerLiveStatus,
    this.timelineAlert,
    this.latestAiTweet,
    this.rawEvents = const [],
  });

  factory LiveSnapshotData.fromJson(Map<String, dynamic> json) {
    final statusMap = <String, PlayerLiveStatusItem>{};
    if (json['player_live_status'] is Map) {
      (json['player_live_status'] as Map).forEach((k, v) {
        if (v is Map<String, dynamic>) {
          statusMap[k.toString()] = PlayerLiveStatusItem.fromJson(v);
        }
      });
    }

    final rawList = <RawEventItem>[];
    if (json['raw_events'] is List) {
      for (final e in json['raw_events'] as List) {
        if (e is Map<String, dynamic>) {
          rawList.add(RawEventItem.fromJson(e));
        }
      }
    }

    return LiveSnapshotData(
      matchId: json['match_id'] as String? ?? '',
      status: json['status'] as String? ?? 'IN_MATCH',
      elapsedMinute: json['elapsed_minute'] as int? ?? 0,
      formattedTime: json['formatted_time'] as String? ?? '00:00',
      score: ScoreBoard.fromJson(
        json['score'] as Map<String, dynamic>? ?? {},
      ),
      winProb: WinProbability.fromJson(
        json['win_prob'] as Map<String, dynamic>? ?? {},
      ),
      metrics: TeamLiveMetrics.fromJson(
        json['metrics'] as Map<String, dynamic>? ?? {},
      ),
      playerLiveStatus: statusMap,
      timelineAlert: json['timeline_alert'] != null
          ? TimelineAlert.fromJson(
              json['timeline_alert'] as Map<String, dynamic>,
            )
          : null,
      latestAiTweet: json['latest_ai_tweet'] != null
          ? AiTweetItem.fromJson(
              json['latest_ai_tweet'] as Map<String, dynamic>,
            )
          : null,
      rawEvents: rawList,
    );
  }
}

class ScoreBoard {
  final int home;
  final int away;

  const ScoreBoard({required this.home, required this.away});

  factory ScoreBoard.fromJson(Map<String, dynamic> json) {
    return ScoreBoard(
      home: json['home'] as int? ?? 0,
      away: json['away'] as int? ?? 0,
    );
  }
}

class WinProbability {
  final double home;
  final double draw;
  final double away;

  const WinProbability({
    required this.home,
    required this.draw,
    required this.away,
  });

  factory WinProbability.fromJson(Map<String, dynamic> json) {
    return WinProbability(
      home: (json['home'] as num?)?.toDouble() ?? 0.33,
      draw: (json['draw'] as num?)?.toDouble() ?? 0.34,
      away: (json['away'] as num?)?.toDouble() ?? 0.33,
    );
  }
}

class TeamLiveMetrics {
  final double homeFieldTilt;
  final double awayFieldTilt;
  final String homeProxyPpda;
  final String awayProxyPpda;
  final int paEntryLeft;
  final int paEntryCenter;
  final int paEntryRight;
  final int shotQualityStars;

  const TeamLiveMetrics({
    this.homeFieldTilt = 0.50,
    this.awayFieldTilt = 0.50,
    this.homeProxyPpda = 'MID',
    this.awayProxyPpda = 'MID',
    this.paEntryLeft = 3,
    this.paEntryCenter = 6,
    this.paEntryRight = 4,
    this.shotQualityStars = 3,
  });

  factory TeamLiveMetrics.fromJson(Map<String, dynamic> json) {
    final tilt = json['field_tilt'] as Map<String, dynamic>? ?? {};
    final ppda = json['proxy_ppda'] as Map<String, dynamic>? ?? {};
    final pa = json['pa_entries'] as Map<String, dynamic>? ?? {};

    return TeamLiveMetrics(
      homeFieldTilt: (tilt['home'] as num?)?.toDouble() ?? 0.50,
      awayFieldTilt: (tilt['away'] as num?)?.toDouble() ?? 0.50,
      homeProxyPpda: ppda['home'] as String? ?? 'MID',
      awayProxyPpda: ppda['away'] as String? ?? 'MID',
      paEntryLeft: pa['left'] as int? ?? 3,
      paEntryCenter: pa['center'] as int? ?? 6,
      paEntryRight: pa['right'] as int? ?? 4,
      shotQualityStars: json['shot_quality_stars'] as int? ?? 3,
    );
  }
}

class PlayerLiveStatusItem {
  final int touchCount10m;
  final int sprintCount5m;
  final String status; // 'normal' | 'faded' | 'overdrive'

  const PlayerLiveStatusItem({
    required this.touchCount10m,
    required this.sprintCount5m,
    required this.status,
  });

  factory PlayerLiveStatusItem.fromJson(Map<String, dynamic> json) {
    return PlayerLiveStatusItem(
      touchCount10m: json['touch_count_10m'] as int? ?? 0,
      sprintCount5m: json['sprint_count_5m'] as int? ?? 0,
      status: json['status'] as String? ?? 'normal',
    );
  }
}

class TimelineAlert {
  final bool active;
  final String title;
  final String message;
  final int targetMinute;

  const TimelineAlert({
    required this.active,
    required this.title,
    required this.message,
    this.targetMinute = 60,
  });

  factory TimelineAlert.fromJson(Map<String, dynamic> json) {
    return TimelineAlert(
      active: json['active'] as bool? ?? false,
      title: json['title'] as String? ?? '',
      message: json['message'] as String? ?? '',
      targetMinute: json['target_minute'] as int? ?? 60,
    );
  }
}

class AiTweetItem {
  final String id;
  final String persona;
  final String speakerName;
  final String text;
  final String timestamp;

  const AiTweetItem({
    required this.id,
    required this.persona,
    required this.speakerName,
    required this.text,
    required this.timestamp,
  });

  factory AiTweetItem.fromJson(Map<String, dynamic> json) {
    return AiTweetItem(
      id: json['id'] as String? ?? '',
      persona: json['persona'] as String? ?? 'tactical_geek',
      speakerName: json['speaker_name'] as String? ?? '戦術オタクの友人',
      text: json['text'] as String? ?? '',
      timestamp: json['timestamp'] as String? ?? "00'",
    );
  }
}

class RawEventItem {
  final String time;
  final String title;
  final String description;
  final String icon;

  const RawEventItem({
    required this.time,
    required this.title,
    required this.description,
    this.icon = '⚽',
  });

  factory RawEventItem.fromJson(Map<String, dynamic> json) {
    return RawEventItem(
      time: json['time'] as String? ?? '',
      title: json['title'] as String? ?? '',
      description: json['description'] as String? ?? '',
      icon: json['icon'] as String? ?? '⚽',
    );
  }
}

/// 開発・検証用の完全モックデータジェネレータ
class MockLiveSnapshot {
  static LiveSnapshotData getSample({int minute = 65}) {
    return LiveSnapshotData(
      matchId: '20261031_OKA_FCT',
      status: 'IN_MATCH',
      elapsedMinute: minute,
      formattedTime: "$minute:24",
      score: const ScoreBoard(home: 1, away: 0),
      winProb: const WinProbability(home: 0.62, draw: 0.25, away: 0.13),
      metrics: const TeamLiveMetrics(
        homeFieldTilt: 0.64,
        awayFieldTilt: 0.36,
        homeProxyPpda: 'HIGH',
        awayProxyPpda: 'LOW',
        paEntryLeft: 4,
        paEntryCenter: 8,
        paEntryRight: 2,
        shotQualityStars: 4,
      ),
      playerLiveStatus: {
        'P_FCT_10': const PlayerLiveStatusItem(
          touchCount10m: 1,
          sprintCount5m: 0,
          status: 'faded', // 消えてる
        ),
        'P_FCT_26': const PlayerLiveStatusItem(
          touchCount10m: 8,
          sprintCount5m: 4,
          status: 'overdrive', // がんばってる
        ),
        'P_OKA_99': const PlayerLiveStatusItem(
          touchCount10m: 6,
          sprintCount5m: 3,
          status: 'overdrive',
        ),
      },
      timelineAlert: const TimelineAlert(
        active: true,
        title: '⚠️ 警戒時間帯 (60〜75分)',
        message: '相手は後半60分以降の被クロス失点率がリーグ最多(38%)。サイドの押し上げに注目！',
        targetMinute: 60,
      ),
      latestAiTweet: const AiTweetItem(
        id: 'tweet_01',
        persona: 'tactical_geek',
        speakerName: '戦術オタクの友人',
        text: '相手、完全に4-4-2のローブロックに切り替えたね。こうなるとサイドバックの押し上げとポケット進入が鍵になるなぁ…',
        timestamp: "63'",
      ),
      rawEvents: const [
        RawEventItem(
          time: "62'",
          title: '選手交代 (FC東京)',
          description: 'OUT: 7 安斎 颯馬 ➔ IN: 19 本間 至恩',
          icon: '🔄',
        ),
        RawEventItem(
          time: "54'",
          title: '枠内シュート (岡山)',
          description: '99 ルカオの強烈なミドルシュート（GK好セーブ）',
          icon: '🧤',
        ),
        RawEventItem(
          time: "38'",
          title: 'GOAL!! (岡山)',
          description: '10 ナ サンホの右足クロスから 99 ルカオのヘディング弾！',
          icon: '⚽',
        ),
        RawEventItem(
          time: "21'",
          title: '警告 (FC東京)',
          description: '20 永野 修都（レイトタックル）',
          icon: '🟨',
        ),
      ],
    );
  }
}
