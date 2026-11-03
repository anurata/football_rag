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

  /// Total points contributed by this action (+1 base for good, -1 for bad, plus bonus points)
  int get netPoints => (actionType == 'good' ? 1 : -1) + bonusPoints;

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
      'created_at': createdAt,
      'is_synced': isSynced ? 1 : 0,
    };
  }
}
