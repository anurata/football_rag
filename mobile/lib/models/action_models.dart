library;

/// User Good/Bad Action model for local persistence and remote sync.

class UserAction {
  final String id;
  final String matchId;
  final String playerId;
  final String? playerName;
  final String teamId;
  final String actionType; // 'good' or 'bad'
  final int matchMinute;
  final String? playCategory;
  final String? note;
  final int bonusPoints;
  final String? createdAt;
  final bool isSynced;

  const UserAction({
    required this.id,
    required this.matchId,
    required this.playerId,
    this.playerName,
    required this.teamId,
    required this.actionType,
    required this.matchMinute,
    this.playCategory,
    this.note,
    this.bonusPoints = 0,
    this.createdAt,
    this.isSynced = false,
  });

  /// Positive points (+1 base for good, plus bonus points)
  int get positivePoints => actionType == 'good' ? (1 + bonusPoints) : 0;

  /// Negative points (+1 base for bad)
  int get negativePoints => actionType == 'bad' ? 1 : 0;

  /// Net points (+ for good, - for bad)
  int get netPoints => positivePoints - negativePoints;

  UserAction copyWith({
    String? id,
    String? matchId,
    String? playerId,
    String? playerName,
    String? teamId,
    String? actionType,
    int? matchMinute,
    String? playCategory,
    String? note,
    int? bonusPoints,
    String? createdAt,
    bool? isSynced,
  }) {
    return UserAction(
      id: id ?? this.id,
      matchId: matchId ?? this.matchId,
      playerId: playerId ?? this.playerId,
      playerName: playerName ?? this.playerName,
      teamId: teamId ?? this.teamId,
      actionType: actionType ?? this.actionType,
      matchMinute: matchMinute ?? this.matchMinute,
      playCategory: playCategory ?? this.playCategory,
      note: note ?? this.note,
      bonusPoints: bonusPoints ?? this.bonusPoints,
      createdAt: createdAt ?? this.createdAt,
      isSynced: isSynced ?? this.isSynced,
    );
  }

  factory UserAction.fromJson(Map<String, dynamic> json) {
    return UserAction(
      id: json['id'] as String? ?? '',
      matchId: json['match_id'] as String? ?? '',
      playerId: json['player_id'] as String? ?? '',
      playerName: json['player_name'] as String?,
      teamId: json['team_id'] as String? ?? '',
      actionType: json['action_type'] as String? ?? 'good',
      matchMinute: json['match_minute'] as int? ?? 0,
      playCategory: json['play_category'] as String?,
      note: json['note'] as String?,
      bonusPoints: json['bonus_points'] as int? ?? 0,
      createdAt: json['created_at'] as String?,
      isSynced: (json['is_synced'] as int? ?? 0) == 1,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'match_id': matchId,
      'player_id': playerId,
      'team_id': teamId,
      'action_type': actionType,
      'match_minute': matchMinute,
      'play_category': playCategory,
      'note': note,
      'bonus_points': bonusPoints,
      'positive_points': positivePoints,
      'negative_points': negativePoints,
      'created_at': createdAt,
    };
  }

  Map<String, dynamic> toDbMap() {
    return {
      'id': id,
      'match_id': matchId,
      'player_id': playerId,
      'player_name': playerName,
      'team_id': teamId,
      'action_type': actionType,
      'match_minute': matchMinute,
      'play_category': playCategory,
      'note': note,
      'bonus_points': bonusPoints,
      'positive_points': positivePoints,
      'negative_points': negativePoints,
      'created_at': createdAt,
      'is_synced': isSynced ? 1 : 0,
    };
  }
}

/// Detailed positive/negative score summary per player
class PlayerScoreSummary {
  final String playerId;
  final int positivePoints;
  final int negativePoints;

  const PlayerScoreSummary({
    required this.playerId,
    this.positivePoints = 0,
    this.negativePoints = 0,
  });

  /// Net score used for badge color calculation (-5 to +15)
  int get netScore => positivePoints - negativePoints;

  PlayerScoreSummary copyWith({
    String? playerId,
    int? positivePoints,
    int? negativePoints,
  }) {
    return PlayerScoreSummary(
      playerId: playerId ?? this.playerId,
      positivePoints: positivePoints ?? this.positivePoints,
      negativePoints: negativePoints ?? this.negativePoints,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'player_id': playerId,
      'positive_points': positivePoints,
      'negative_points': negativePoints,
      'net_score': netScore,
    };
  }

  factory PlayerScoreSummary.fromJson(Map<String, dynamic> json) {
    return PlayerScoreSummary(
      playerId: json['player_id'] as String? ?? '',
      positivePoints: json['positive_points'] as int? ?? 0,
      negativePoints: json['negative_points'] as int? ?? 0,
    );
  }
}
