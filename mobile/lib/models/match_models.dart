library;

/// Match and player context models matching backend FastAPI schemas.

class PlayerContextItem {
  final String playerId;
  final String playerName;
  final String? shortName;
  final int number;
  final String position;
  final bool isStarter;
  final double pitchX;
  final double pitchY;
  final String? photoUrl;

  const PlayerContextItem({
    required this.playerId,
    required this.playerName,
    this.shortName,
    required this.number,
    required this.position,
    required this.isStarter,
    required this.pitchX,
    required this.pitchY,
    this.photoUrl,
  });

  /// Get compact display name suitable for mobile pitch pin card
  String get displayName {
    if (shortName != null && shortName!.trim().isNotEmpty) {
      return shortName!;
    }
    // Fallback if shortName not provided by server
    const knownShortNames = {
      'バングーナガンデ 佳史扶': 'バングーナガンデ',
      'アレクサンダー ショルツ': 'ショルツ',
      'ブラウンノア 賢信': 'ブラウンノア',
      'レナート モーザー': 'モーザー',
      'ダニ ゴメス': 'ダニ ゴメス',
      'キム スンギュ': 'キム スンギュ',
      'ナ サンホ': 'ナ サンホ',
      'レオ ガウショ': 'レオ ガウショ',
    };
    if (knownShortNames.containsKey(playerName)) {
      return knownShortNames[playerName]!;
    }
    final parts = playerName.split(' ');
    if (parts.length >= 2 && playerName.length > 5) {
      return parts[0];
    }
    return playerName;
  }

  factory PlayerContextItem.fromJson(Map<String, dynamic> json) {
    return PlayerContextItem(
      playerId: json['player_id'] as String? ?? '',
      playerName: json['player_name'] as String? ?? '',
      shortName: json['short_name'] as String?,
      number: json['number'] as int? ?? 0,
      position: json['position'] as String? ?? 'MF',
      isStarter: json['is_starter'] as bool? ?? true,
      pitchX: (json['pitch_x'] as num?)?.toDouble() ?? 50.0,
      pitchY: (json['pitch_y'] as num?)?.toDouble() ?? 50.0,
      photoUrl: json['photo_url'] as String?,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'player_id': playerId,
      'player_name': playerName,
      'short_name': shortName,
      'number': number,
      'position': position,
      'is_starter': isStarter,
      'pitch_x': pitchX,
      'pitch_y': pitchY,
      'photo_url': photoUrl,
    };
  }

  PlayerContextItem copyWith({
    String? playerId,
    String? playerName,
    String? shortName,
    int? number,
    String? position,
    bool? isStarter,
    double? pitchX,
    double? pitchY,
    String? photoUrl,
  }) {
    return PlayerContextItem(
      playerId: playerId ?? this.playerId,
      playerName: playerName ?? this.playerName,
      shortName: shortName ?? this.shortName,
      number: number ?? this.number,
      position: position ?? this.position,
      isStarter: isStarter ?? this.isStarter,
      pitchX: pitchX ?? this.pitchX,
      pitchY: pitchY ?? this.pitchY,
      photoUrl: photoUrl ?? this.photoUrl,
    );
  }
}

class TeamContextItem {
  final String teamId;
  final String teamName;
  final String shortName;
  final int score;
  final String formation;
  final List<PlayerContextItem> starters;
  final List<PlayerContextItem> bench;

  const TeamContextItem({
    required this.teamId,
    required this.teamName,
    required this.shortName,
    required this.score,
    required this.formation,
    required this.starters,
    required this.bench,
  });

  factory TeamContextItem.fromJson(Map<String, dynamic> json) {
    final rawStarters = json['starters'] as List<dynamic>? ?? [];
    final rawBench = json['bench'] as List<dynamic>? ?? [];

    return TeamContextItem(
      teamId: json['team_id'] as String? ?? '',
      teamName: json['team_name'] as String? ?? '',
      shortName: json['short_name'] as String? ?? '',
      score: json['score'] as int? ?? 0,
      formation: json['formation'] as String? ?? '4-2-3-1',
      starters: rawStarters
          .map((e) => PlayerContextItem.fromJson(e as Map<String, dynamic>))
          .toList(),
      bench: rawBench
          .map((e) => PlayerContextItem.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'team_id': teamId,
      'team_name': teamName,
      'short_name': shortName,
      'score': score,
      'formation': formation,
      'starters': starters.map((e) => e.toJson()).toList(),
      'bench': bench.map((e) => e.toJson()).toList(),
    };
  }

  TeamContextItem copyWith({
    String? teamId,
    String? teamName,
    String? shortName,
    int? score,
    String? formation,
    List<PlayerContextItem>? starters,
    List<PlayerContextItem>? bench,
  }) {
    return TeamContextItem(
      teamId: teamId ?? this.teamId,
      teamName: teamName ?? this.teamName,
      shortName: shortName ?? this.shortName,
      score: score ?? this.score,
      formation: formation ?? this.formation,
      starters: starters ?? this.starters,
      bench: bench ?? this.bench,
    );
  }

  /// Returns appropriate display name. If multiple players in the team share the same last name,
  /// returns the full name to clearly distinguish them on the pitch.
  String getPlayerDisplayName(PlayerContextItem player) {
    final allPlayers = [...starters, ...bench];
    final parts = player.playerName.trim().split(RegExp(r'\s+'));
    if (parts.length >= 2) {
      final lastName = parts.first;
      final duplicateCount = allPlayers.where((p) {
        final pParts = p.playerName.trim().split(RegExp(r'\s+'));
        return pParts.isNotEmpty && pParts.first == lastName;
      }).length;
      if (duplicateCount > 1) {
        return player.playerName;
      }
    }
    return player.displayName;
  }
}

class MatchAppContext {
  final String matchId;
  final int season;
  final int matchweek;
  final String date;
  final String stadium;
  final String? weather;
  final String status;
  final TeamContextItem homeTeam;
  final TeamContextItem awayTeam;
  final Map<String, dynamic> tacticalPreview;
  final Map<String, dynamic> liveStats;

  const MatchAppContext({
    required this.matchId,
    required this.season,
    required this.matchweek,
    required this.date,
    required this.stadium,
    this.weather,
    required this.status,
    required this.homeTeam,
    required this.awayTeam,
    required this.tacticalPreview,
    required this.liveStats,
  });

  factory MatchAppContext.fromJson(Map<String, dynamic> json) {
    return MatchAppContext(
      matchId: json['match_id'] as String? ?? '',
      season: json['season'] as int? ?? 2026,
      matchweek: json['matchweek'] as int? ?? 1,
      date: json['date'] as String? ?? '',
      stadium: json['stadium'] as String? ?? '',
      weather: json['weather'] as String?,
      status: json['status'] as String? ?? 'PRE',
      homeTeam: TeamContextItem.fromJson(
        json['home_team'] as Map<String, dynamic>? ?? {},
      ),
      awayTeam: TeamContextItem.fromJson(
        json['away_team'] as Map<String, dynamic>? ?? {},
      ),
      tacticalPreview: json['tactical_preview'] as Map<String, dynamic>? ?? {},
      liveStats: json['live_stats'] as Map<String, dynamic>? ?? {},
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'match_id': matchId,
      'season': season,
      'matchweek': matchweek,
      'date': date,
      'stadium': stadium,
      'weather': weather,
      'status': status,
      'home_team': homeTeam.toJson(),
      'away_team': awayTeam.toJson(),
      'tactical_preview': tacticalPreview,
      'live_stats': liveStats,
    };
  }

  MatchAppContext copyWith({
    String? matchId,
    int? season,
    int? matchweek,
    String? date,
    String? stadium,
    String? weather,
    String? status,
    TeamContextItem? homeTeam,
    TeamContextItem? awayTeam,
    Map<String, dynamic>? tacticalPreview,
    Map<String, dynamic>? liveStats,
  }) {
    return MatchAppContext(
      matchId: matchId ?? this.matchId,
      season: season ?? this.season,
      matchweek: matchweek ?? this.matchweek,
      date: date ?? this.date,
      stadium: stadium ?? this.stadium,
      weather: weather ?? this.weather,
      status: status ?? this.status,
      homeTeam: homeTeam ?? this.homeTeam,
      awayTeam: awayTeam ?? this.awayTeam,
      tacticalPreview: tacticalPreview ?? this.tacticalPreview,
      liveStats: liveStats ?? this.liveStats,
    );
  }
}

/// Represents an aggregated rating entry for ranking display
class PlayerRankingEntry {
  final PlayerContextItem player;
  final int rank;
  final int netScore;
  final int positivePoints;
  final int negativePoints;
  final int actionCount;

  const PlayerRankingEntry({
    required this.player,
    required this.rank,
    required this.netScore,
    required this.positivePoints,
    required this.negativePoints,
    required this.actionCount,
  });
}
