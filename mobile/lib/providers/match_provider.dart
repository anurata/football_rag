import 'dart:async';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:uuid/uuid.dart';

import '../models/action_models.dart';
import '../models/match_models.dart';
import '../services/api_client.dart';
import '../services/local_db.dart';

final apiClientProvider = Provider<ApiClient>((ref) {
  return ApiClient();
});

final localDbProvider = Provider<LocalDbService>((ref) {
  return LocalDbService.instance;
});

class MatchTrackingState {
  final MatchAppContext? matchContext;
  final bool isLoading;
  final String selectedTeam; // 'HOME' or 'AWAY'
  final int elapsedSeconds; // Stopwatch seconds
  final bool isTimerRunning;
  final List<UserAction> recentActions;
  final bool isSyncing;
  final String syncStatusMessage;

  const MatchTrackingState({
    this.matchContext,
    this.isLoading = false,
    this.selectedTeam = 'HOME',
    this.elapsedSeconds = 0,
    this.isTimerRunning = false,
    this.recentActions = const [],
    this.isSyncing = false,
    this.syncStatusMessage = 'Ready',
  });

  /// Current minute (e.g. 0' at 0-59s, 45' at 45:00)
  int get currentMinute => (elapsedSeconds / 60).floor();

  /// Formatted mm:ss string (e.g. "00:00", "45:12")
  String get formattedTime {
    final m = (elapsedSeconds / 60).floor().toString().padLeft(2, '0');
    final s = (elapsedSeconds % 60).toString().padLeft(2, '0');
    return '$m:$s';
  }

  /// True if over 45 minutes (triggers orange background)
  bool get isOver45Minutes => elapsedSeconds >= 45 * 60;

  /// Detailed positive and negative points per player
  Map<String, PlayerScoreSummary> get playerScoresDetailed {
    final map = <String, PlayerScoreSummary>{};
    for (final act in recentActions) {
      final existing = map[act.playerId] ??
          PlayerScoreSummary(playerId: act.playerId);
      map[act.playerId] = existing.copyWith(
        positivePoints: existing.positivePoints + act.positivePoints,
        negativePoints: existing.negativePoints + act.negativePoints,
      );
    }
    return map;
  }

  /// Real-time net score per player across recorded actions
  Map<String, int> get playerScores {
    return playerScoresDetailed.map((k, v) => MapEntry(k, v.netScore));
  }

  MatchTrackingState copyWith({
    MatchAppContext? matchContext,
    bool? isLoading,
    String? selectedTeam,
    int? elapsedSeconds,
    bool? isTimerRunning,
    List<UserAction>? recentActions,
    bool? isSyncing,
    String? syncStatusMessage,
  }) {
    return MatchTrackingState(
      matchContext: matchContext ?? this.matchContext,
      isLoading: isLoading ?? this.isLoading,
      selectedTeam: selectedTeam ?? this.selectedTeam,
      elapsedSeconds: elapsedSeconds ?? this.elapsedSeconds,
      isTimerRunning: isTimerRunning ?? this.isTimerRunning,
      recentActions: recentActions ?? this.recentActions,
      isSyncing: isSyncing ?? this.isSyncing,
      syncStatusMessage: syncStatusMessage ?? this.syncStatusMessage,
    );
  }
}

class MatchTrackingNotifier extends Notifier<MatchTrackingState> {
  late final ApiClient _apiClient;
  late final LocalDbService _localDb;
  final _uuid = const Uuid();
  Timer? _stopwatchTimer;

  @override
  MatchTrackingState build() {
    _apiClient = ref.watch(apiClientProvider);
    _localDb = ref.watch(localDbProvider);
    ref.onDispose(() => _stopTimer());
    return const MatchTrackingState();
  }

  void toggleTimer() {
    if (state.isTimerRunning) {
      _stopTimer();
    } else {
      _startTimer();
    }
  }

  void _startTimer() {
    _stopwatchTimer?.cancel();
    state = state.copyWith(isTimerRunning: true);
    _stopwatchTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      final nextSec = state.elapsedSeconds + 1;
      if (nextSec >= 60 * 60) {
        // Automatically stop at 60:00
        _stopTimer();
        state = state.copyWith(elapsedSeconds: 60 * 60);
      } else {
        state = state.copyWith(elapsedSeconds: nextSec);
      }
    });
  }

  void _stopTimer() {
    _stopwatchTimer?.cancel();
    _stopwatchTimer = null;
    state = state.copyWith(isTimerRunning: false);
  }

  void adjustMinutes(int deltaMinutes) {
    if (state.isTimerRunning) return; // Only allow adjusting when paused
    final currentMin = (state.elapsedSeconds / 60).floor();
    final newMin = (currentMin + deltaMinutes).clamp(0, 60);
    state = state.copyWith(elapsedSeconds: newMin * 60);
  }

  void setElapsedSeconds(int seconds) {
    _stopTimer();
    state = state.copyWith(elapsedSeconds: seconds.clamp(0, 60 * 60));
  }

  void incrementMinute() => adjustMinutes(1);

  void setMinute(int min) => setElapsedSeconds(min * 60);

  Future<void> loadMatch(String matchId) async {
    state = state.copyWith(isLoading: true);

    // 1. Load locally cached actions first
    final localActions = await _localDb.getActionsForMatch(matchId);

    // 2. Fetch context from server
    final remoteCtx = await _apiClient.fetchMatchAppContext(matchId);

    // 3. Fallback mock context if server offline
    final effectiveCtx = remoteCtx ?? _generateFallbackContext(matchId);

    state = state.copyWith(
      matchContext: effectiveCtx,
      isLoading: false,
      recentActions: localActions,
      syncStatusMessage: remoteCtx != null ? 'Online' : 'Offline Mode',
    );

    // 4. Background sync if any unsynced actions exist
    _trySyncPendingActions();
  }

  void switchTeam(String team) {
    if (state.selectedTeam != team) {
      state = state.copyWith(selectedTeam: team);
    }
  }

  Future<void> recordAction({
    required String playerId,
    required String playerName,
    required String teamId,
    required String actionType,
    String? playCategory,
    String? note,
  }) async {
    final actionId = _uuid.v4();
    final matchId = state.matchContext?.matchId ?? 'M_UNKNOWN';
    final now = DateTime.now().toIso8601String();

    final action = UserAction(
      id: actionId,
      matchId: matchId,
      playerId: playerId,
      playerName: playerName,
      teamId: teamId,
      actionType: actionType,
      matchMinute: state.currentMinute,
      playCategory: playCategory,
      note: note,
      createdAt: now,
      isSynced: false,
    );

    // 1. Immediately persist locally (Local-First: zero latency)
    await _localDb.insertAction(action);

    // 2. Update UI instantly
    final updatedList = [action, ...state.recentActions];
    state = state.copyWith(recentActions: updatedList);

    // 3. Asynchronously push to server
    _trySyncPendingActions();
  }

  Future<void> incrementActionBonus(String actionId) async {
    final idx = state.recentActions.indexWhere((a) => a.id == actionId);
    if (idx == -1) return;

    final target = state.recentActions[idx];
    final updated = target.copyWith(bonusPoints: target.bonusPoints + 1);

    await _localDb.updateBonusPoints(actionId, updated.bonusPoints);

    final newList = List<UserAction>.from(state.recentActions);
    newList[idx] = updated;
    state = state.copyWith(recentActions: newList);

    _trySyncPendingActions();
  }

  Future<void> removeAction(String actionId) async {
    await _localDb.deleteAction(actionId);

    final newList = state.recentActions.where((a) => a.id != actionId).toList();
    state = state.copyWith(recentActions: newList);
  }

  void substitutePlayer({
    required String teamId,
    required String outPlayerId,
    required String inPlayerId,
  }) {
    final ctx = state.matchContext;
    if (ctx == null) return;

    final isHome = teamId == ctx.homeTeam.teamId || teamId == 'HOME';
    final targetTeam = isHome ? ctx.homeTeam : ctx.awayTeam;

    final outIdx = targetTeam.starters.indexWhere((p) => p.playerId == outPlayerId);
    final inIdx = targetTeam.bench.indexWhere((p) => p.playerId == inPlayerId);
    if (outIdx == -1 || inIdx == -1) return;

    final outPlayer = targetTeam.starters[outIdx];
    final inPlayer = targetTeam.bench[inIdx];

    final updatedInPlayer = inPlayer.copyWith(
      position: outPlayer.position,
      pitchX: outPlayer.pitchX,
      pitchY: outPlayer.pitchY,
      isStarter: true,
    );

    final updatedOutPlayer = outPlayer.copyWith(
      isStarter: false,
    );

    final newStarters = List<PlayerContextItem>.from(targetTeam.starters);
    newStarters[outIdx] = updatedInPlayer;

    final newBench = List<PlayerContextItem>.from(targetTeam.bench);
    newBench[inIdx] = updatedOutPlayer;

    final updatedTeam = targetTeam.copyWith(
      starters: newStarters,
      bench: newBench,
    );

    final updatedCtx = isHome
        ? ctx.copyWith(homeTeam: updatedTeam)
        : ctx.copyWith(awayTeam: updatedTeam);

    state = state.copyWith(matchContext: updatedCtx);

    recordAction(
      playerId: inPlayer.playerId,
      playerName: inPlayer.displayName,
      teamId: targetTeam.teamId,
      actionType: 'sub',
      playCategory: '交代',
      note: '🔄 交代: IN #${inPlayer.number} ${inPlayer.displayName} / OUT #${outPlayer.number} ${outPlayer.displayName}',
    );
  }

  void swapPositions({
    required String teamId,
    required String player1Id,
    required String player2Id,
  }) {
    final ctx = state.matchContext;
    if (ctx == null) return;

    final isHome = teamId == ctx.homeTeam.teamId || teamId == 'HOME';
    final targetTeam = isHome ? ctx.homeTeam : ctx.awayTeam;

    final idx1 = targetTeam.starters.indexWhere((p) => p.playerId == player1Id);
    final idx2 = targetTeam.starters.indexWhere((p) => p.playerId == player2Id);
    if (idx1 == -1 || idx2 == -1 || idx1 == idx2) return;

    final p1 = targetTeam.starters[idx1];
    final p2 = targetTeam.starters[idx2];

    final updatedP1 = p1.copyWith(
      position: p2.position,
      pitchX: p2.pitchX,
      pitchY: p2.pitchY,
    );

    final updatedP2 = p2.copyWith(
      position: p1.position,
      pitchX: p1.pitchX,
      pitchY: p1.pitchY,
    );

    final newStarters = List<PlayerContextItem>.from(targetTeam.starters);
    newStarters[idx1] = updatedP1;
    newStarters[idx2] = updatedP2;

    final updatedTeam = targetTeam.copyWith(starters: newStarters);
    final updatedCtx = isHome
        ? ctx.copyWith(homeTeam: updatedTeam)
        : ctx.copyWith(awayTeam: updatedTeam);

    state = state.copyWith(matchContext: updatedCtx);

    recordAction(
      playerId: p1.playerId,
      playerName: p1.displayName,
      teamId: targetTeam.teamId,
      actionType: 'swap',
      playCategory: '位置変更',
      note: '⇄ 入替: #${p1.number} ${p1.displayName} (${p1.position}→${p2.position}) ↔ #${p2.number} ${p2.displayName} (${p2.position}→${p1.position})',
    );
  }

  List<PlayerRankingEntry> getRankings({required String teamId}) {
    final ctx = state.matchContext;
    if (ctx == null) return const [];

    final isHome = teamId == ctx.homeTeam.teamId || teamId == 'HOME';
    final targetTeam = isHome ? ctx.homeTeam : ctx.awayTeam;

    final allPlayers = [...targetTeam.starters, ...targetTeam.bench];
    final scoresMap = state.playerScoresDetailed;

    final actionCounts = <String, int>{};
    for (final act in state.recentActions) {
      if (act.actionType == 'good' || act.actionType == 'bad') {
        actionCounts[act.playerId] = (actionCounts[act.playerId] ?? 0) + 1;
      }
    }

    final entries = allPlayers.map((player) {
      final summary = scoresMap[player.playerId] ??
          PlayerScoreSummary(playerId: player.playerId);
      final count = actionCounts[player.playerId] ?? 0;
      return PlayerRankingEntry(
        player: player,
        rank: 1,
        netScore: summary.netScore,
        positivePoints: summary.positivePoints,
        negativePoints: summary.negativePoints,
        actionCount: count,
      );
    }).toList();

    entries.sort((a, b) {
      if (b.netScore != a.netScore) {
        return b.netScore.compareTo(a.netScore);
      }
      if (b.positivePoints != a.positivePoints) {
        return b.positivePoints.compareTo(a.positivePoints);
      }
      if (b.actionCount != a.actionCount) {
        return b.actionCount.compareTo(a.actionCount);
      }
      return a.player.number.compareTo(b.player.number);
    });

    final rankedList = <PlayerRankingEntry>[];
    int currentRank = 1;
    for (int i = 0; i < entries.length; i++) {
      if (i > 0) {
        final prev = entries[i - 1];
        final curr = entries[i];
        if (curr.netScore != prev.netScore ||
            curr.positivePoints != prev.positivePoints) {
          currentRank = i + 1;
        }
      }
      rankedList.add(
        PlayerRankingEntry(
          player: entries[i].player,
          rank: currentRank,
          netScore: entries[i].netScore,
          positivePoints: entries[i].positivePoints,
          negativePoints: entries[i].negativePoints,
          actionCount: entries[i].actionCount,
        ),
      );
    }

    return rankedList;
  }

  Future<void> _trySyncPendingActions() async {
    final unsynced = await _localDb.getUnsyncedActions();
    if (unsynced.isEmpty) return;

    state = state.copyWith(isSyncing: true);
    final success = await _apiClient.syncActions(unsynced);

    if (success) {
      await _localDb.markActionsSynced(unsynced.map((a) => a.id).toList());
      state = state.copyWith(
        isSyncing: false,
        syncStatusMessage: 'Synced (${unsynced.length})',
      );
    } else {
      state = state.copyWith(
        isSyncing: false,
        syncStatusMessage: 'Pending sync (${unsynced.length})',
      );
    }
  }

  MatchAppContext _generateFallbackContext(String matchId) {
    return MatchAppContext(
      matchId: matchId.isNotEmpty ? matchId : '20261031_OKA_FCT',
      season: 2026,
      matchweek: 13,
      date: '2026-10-31',
      stadium: 'シティライトスタジアム',
      status: 'FINISHED',
      homeTeam: _buildOkayamaFallback(),
      awayTeam: _buildFcTokyoFallback(),
      tacticalPreview: const {
        'headline': '明治安田J1 第13節 岡山 vs FC東京',
      },
      liveStats: const {
        'home_score': 0,
        'away_score': 4,
      },
    );
  }

  TeamContextItem _buildOkayamaFallback() {
    const starters = [
      PlayerContextItem(
        playerId: 'P_OKA_52_濱田太郎',
        playerName: '濱田 太郎',
        shortName: '濱田',
        number: 52,
        position: 'GK',
        isStarter: true,
        pitchX: 50.0,
        pitchY: 88.0,
      ),
      PlayerContextItem(
        playerId: 'P_OKA_43_鈴木喜丈',
        playerName: '鈴木 喜丈',
        shortName: '鈴木',
        number: 43,
        position: 'LCB',
        isStarter: true,
        pitchX: 24.0,
        pitchY: 70.0,
      ),
      PlayerContextItem(
        playerId: 'P_OKA_44_森壮一朗',
        playerName: '森 壮一朗',
        shortName: '森',
        number: 44,
        position: 'CB',
        isStarter: true,
        pitchX: 50.0,
        pitchY: 70.0,
      ),
      PlayerContextItem(
        playerId: 'P_OKA_48_立田悠悟',
        playerName: '立田 悠悟',
        shortName: '立田',
        number: 48,
        position: 'RCB',
        isStarter: true,
        pitchX: 76.0,
        pitchY: 70.0,
      ),
      PlayerContextItem(
        playerId: 'P_OKA_26_本山遥',
        playerName: '本山 遥',
        shortName: '本山',
        number: 26,
        position: 'LWB',
        isStarter: true,
        pitchX: 12.0,
        pitchY: 52.0,
      ),
      PlayerContextItem(
        playerId: 'P_OKA_41_宮本英治',
        playerName: '宮本 英治',
        shortName: '宮本',
        number: 41,
        position: 'LCM',
        isStarter: true,
        pitchX: 38.0,
        pitchY: 52.0,
      ),
      PlayerContextItem(
        playerId: 'P_OKA_80_オベルダン',
        playerName: 'オベルダン',
        shortName: 'オベルダン',
        number: 80,
        position: 'RCM',
        isStarter: true,
        pitchX: 62.0,
        pitchY: 52.0,
      ),
      PlayerContextItem(
        playerId: 'P_OKA_51_白井康介',
        playerName: '白井 康介',
        shortName: '白井',
        number: 51,
        position: 'RWB',
        isStarter: true,
        pitchX: 88.0,
        pitchY: 52.0,
      ),
      PlayerContextItem(
        playerId: 'P_OKA_8_江坂任',
        playerName: '江坂 任',
        shortName: '江坂',
        number: 8,
        position: 'LOM',
        isStarter: true,
        pitchX: 32.0,
        pitchY: 34.0,
      ),
      PlayerContextItem(
        playerId: 'P_OKA_10_ナサンホ',
        playerName: 'ナ サンホ',
        shortName: 'ナ サンホ',
        number: 10,
        position: 'ROM',
        isStarter: true,
        pitchX: 68.0,
        pitchY: 34.0,
      ),
      PlayerContextItem(
        playerId: 'P_OKA_99_ルカオ',
        playerName: 'ルカオ',
        shortName: 'ルカオ',
        number: 99,
        position: 'CF',
        isStarter: true,
        pitchX: 50.0,
        pitchY: 16.0,
      ),
    ];

    const bench = [
      PlayerContextItem(
        playerId: 'P_OKA_1_レナートモーザー',
        playerName: 'レナート モーザー',
        shortName: 'モーザー',
        number: 1,
        position: 'GK',
        isStarter: false,
        pitchX: 50.0,
        pitchY: 50.0,
      ),
      PlayerContextItem(
        playerId: 'P_OKA_55_藤井葉大',
        playerName: '藤井 葉大',
        shortName: '藤井',
        number: 55,
        position: 'DF',
        isStarter: false,
        pitchX: 50.0,
        pitchY: 50.0,
      ),
      PlayerContextItem(
        playerId: 'P_OKA_7_竹内涼',
        playerName: '竹内 涼',
        shortName: '竹内',
        number: 7,
        position: 'MF',
        isStarter: false,
        pitchX: 50.0,
        pitchY: 50.0,
      ),
      PlayerContextItem(
        playerId: 'P_OKA_24_藤田息吹',
        playerName: '藤田 息吹',
        shortName: '藤田',
        number: 24,
        position: 'MF',
        isStarter: false,
        pitchX: 50.0,
        pitchY: 50.0,
      ),
      PlayerContextItem(
        playerId: 'P_OKA_28_松本昌也',
        playerName: '松本 昌也',
        shortName: '松本',
        number: 28,
        position: 'MF',
        isStarter: false,
        pitchX: 50.0,
        pitchY: 50.0,
      ),
      PlayerContextItem(
        playerId: 'P_OKA_79_ブラウンノア賢信',
        playerName: 'ブラウンノア 賢信',
        shortName: 'ブラウンノア',
        number: 79,
        position: 'MF',
        isStarter: false,
        pitchX: 50.0,
        pitchY: 50.0,
      ),
      PlayerContextItem(
        playerId: 'P_OKA_88_山根永遠',
        playerName: '山根 永遠',
        shortName: '山根',
        number: 88,
        position: 'MF',
        isStarter: false,
        pitchX: 50.0,
        pitchY: 50.0,
      ),
      PlayerContextItem(
        playerId: 'P_OKA_9_レオガウショ',
        playerName: 'レオ ガウショ',
        shortName: 'レオ ガウショ',
        number: 9,
        position: 'FW',
        isStarter: false,
        pitchX: 50.0,
        pitchY: 50.0,
      ),
      PlayerContextItem(
        playerId: 'P_OKA_20_河野孝汰',
        playerName: '河野 孝汰',
        shortName: '河野',
        number: 20,
        position: 'FW',
        isStarter: false,
        pitchX: 50.0,
        pitchY: 50.0,
      ),
    ];

    return const TeamContextItem(
      teamId: 'OKA',
      teamName: 'ファジアーノ岡山',
      shortName: '岡山',
      score: 0,
      formation: '3-4-2-1',
      starters: starters,
      bench: bench,
    );
  }

  TeamContextItem _buildFcTokyoFallback() {
    const starters = [
      PlayerContextItem(
        playerId: 'P_FCT_81_キムスンギュ',
        playerName: 'キム スンギュ',
        shortName: 'キム スンギュ',
        number: 81,
        position: 'GK',
        isStarter: true,
        pitchX: 50.0,
        pitchY: 89.0,
      ),
      PlayerContextItem(
        playerId: 'P_FCT_6_バングーナガンデ佳史扶',
        playerName: 'バングーナガンデ 佳史扶',
        shortName: 'バングーナガンデ',
        number: 6,
        position: 'LSB',
        isStarter: true,
        pitchX: 14.0,
        pitchY: 66.0,
      ),
      PlayerContextItem(
        playerId: 'P_FCT_4_稲村隼翔',
        playerName: '稲村 隼翔',
        shortName: '稲村',
        number: 4,
        position: 'LCB',
        isStarter: true,
        pitchX: 38.0,
        pitchY: 66.0,
      ),
      PlayerContextItem(
        playerId: 'P_FCT_24_アレクサンダーショルツ',
        playerName: 'アレクサンダー ショルツ',
        shortName: 'ショルツ',
        number: 24,
        position: 'RCB',
        isStarter: true,
        pitchX: 62.0,
        pitchY: 66.0,
      ),
      PlayerContextItem(
        playerId: 'P_FCT_22_石原広教',
        playerName: '石原 広教',
        shortName: '石原',
        number: 22,
        position: 'RSB',
        isStarter: true,
        pitchX: 86.0,
        pitchY: 66.0,
      ),
      PlayerContextItem(
        playerId: 'P_FCT_7_安斎颯馬',
        playerName: '安斎 颯馬',
        shortName: '安斎',
        number: 7,
        position: 'LSH',
        isStarter: true,
        pitchX: 14.0,
        pitchY: 43.0,
      ),
      PlayerContextItem(
        playerId: 'P_FCT_8_高宇洋',
        playerName: '高 宇洋',
        shortName: '高 宇洋',
        number: 8,
        position: 'LCM',
        isStarter: true,
        pitchX: 38.0,
        pitchY: 43.0,
      ),
      PlayerContextItem(
        playerId: 'P_FCT_20_永野修都',
        playerName: '永野 修都',
        shortName: '永野',
        number: 20,
        position: 'RCM',
        isStarter: true,
        pitchX: 62.0,
        pitchY: 43.0,
      ),
      PlayerContextItem(
        playerId: 'P_FCT_10_佐藤恵允',
        playerName: '佐藤 恵允',
        shortName: '佐藤',
        number: 10,
        position: 'RSH',
        isStarter: true,
        pitchX: 86.0,
        pitchY: 43.0,
      ),
      PlayerContextItem(
        playerId: 'P_FCT_26_長倉幹樹',
        playerName: '長倉 幹樹',
        shortName: '長倉',
        number: 26,
        position: 'LCF',
        isStarter: true,
        pitchX: 35.0,
        pitchY: 20.0,
      ),
      PlayerContextItem(
        playerId: 'P_FCT_39_仲川輝人',
        playerName: '仲川 輝人',
        shortName: '仲川',
        number: 39,
        position: 'RCF',
        isStarter: true,
        pitchX: 65.0,
        pitchY: 20.0,
      ),
    ];

    const bench = [
      PlayerContextItem(
        playerId: 'P_FCT_1_田中颯',
        playerName: '田中 颯',
        shortName: '田中',
        number: 1,
        position: 'GK',
        isStarter: false,
        pitchX: 50.0,
        pitchY: 50.0,
      ),
      PlayerContextItem(
        playerId: 'P_FCT_3_森重真人',
        playerName: '森重 真人',
        shortName: '森重',
        number: 3,
        position: 'DF',
        isStarter: false,
        pitchX: 50.0,
        pitchY: 50.0,
      ),
      PlayerContextItem(
        playerId: 'P_FCT_15_大森理生',
        playerName: '大森 理生',
        shortName: '大森',
        number: 15,
        position: 'DF',
        isStarter: false,
        pitchX: 50.0,
        pitchY: 50.0,
      ),
      PlayerContextItem(
        playerId: 'P_FCT_42_橋本健人',
        playerName: '橋本 健人',
        shortName: '橋本',
        number: 42,
        position: 'DF',
        isStarter: false,
        pitchX: 50.0,
        pitchY: 50.0,
      ),
      PlayerContextItem(
        playerId: 'P_FCT_44_鈴木楓',
        playerName: '鈴木 楓',
        shortName: '鈴木楓',
        number: 44,
        position: 'DF',
        isStarter: false,
        pitchX: 50.0,
        pitchY: 50.0,
      ),
      PlayerContextItem(
        playerId: 'P_FCT_19_本間至恩',
        playerName: '本間 至恩',
        shortName: '本間',
        number: 19,
        position: 'MF',
        isStarter: false,
        pitchX: 50.0,
        pitchY: 50.0,
      ),
      PlayerContextItem(
        playerId: 'P_FCT_33_俵積田晃太',
        playerName: '俵積田 晃太',
        shortName: '俵積田',
        number: 33,
        position: 'MF',
        isStarter: false,
        pitchX: 50.0,
        pitchY: 50.0,
      ),
      PlayerContextItem(
        playerId: 'P_FCT_71_山田楓喜',
        playerName: '山田 楓喜',
        shortName: '山田',
        number: 71,
        position: 'MF',
        isStarter: false,
        pitchX: 50.0,
        pitchY: 50.0,
      ),
      PlayerContextItem(
        playerId: 'P_FCT_99_ダニゴメス',
        playerName: 'ダニ ゴメス',
        shortName: 'ダニ ゴメス',
        number: 99,
        position: 'FW',
        isStarter: false,
        pitchX: 50.0,
        pitchY: 50.0,
      ),
    ];

    return const TeamContextItem(
      teamId: 'FCT',
      teamName: 'FC東京',
      shortName: 'FC東京',
      score: 4,
      formation: '4-4-2',
      starters: starters,
      bench: bench,
    );
  }
}

final matchTrackingProvider =
    NotifierProvider<MatchTrackingNotifier, MatchTrackingState>(
  MatchTrackingNotifier.new,
);
