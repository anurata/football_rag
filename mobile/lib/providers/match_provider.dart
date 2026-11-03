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
  final int currentMinute;
  final List<UserAction> recentActions;
  final bool isSyncing;
  final String syncStatusMessage;

  const MatchTrackingState({
    this.matchContext,
    this.isLoading = false,
    this.selectedTeam = 'HOME',
    this.currentMinute = 0,
    this.recentActions = const [],
    this.isSyncing = false,
    this.syncStatusMessage = 'Ready',
  });

  MatchTrackingState copyWith({
    MatchAppContext? matchContext,
    bool? isLoading,
    String? selectedTeam,
    int? currentMinute,
    List<UserAction>? recentActions,
    bool? isSyncing,
    String? syncStatusMessage,
  }) {
    return MatchTrackingState(
      matchContext: matchContext ?? this.matchContext,
      isLoading: isLoading ?? this.isLoading,
      selectedTeam: selectedTeam ?? this.selectedTeam,
      currentMinute: currentMinute ?? this.currentMinute,
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

  @override
  MatchTrackingState build() {
    _apiClient = ref.watch(apiClientProvider);
    _localDb = ref.watch(localDbProvider);
    return const MatchTrackingState();
  }

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

  void incrementMinute() {
    state = state.copyWith(currentMinute: state.currentMinute + 1);
  }

  void setMinute(int min) {
    state = state.copyWith(currentMinute: min);
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
    final tokyoStarters = [
      const PlayerContextItem(
        playerId: 'P_FCT_37',
        playerName: '小泉 慶',
        number: 37,
        position: 'DMF',
        isStarter: true,
        pitchX: 45.0,
        pitchY: 55.0,
      ),
      const PlayerContextItem(
        playerId: 'P_FCT_8',
        playerName: '高 宇洋',
        number: 8,
        position: 'DMF',
        isStarter: true,
        pitchX: 65.0,
        pitchY: 55.0,
      ),
      const PlayerContextItem(
        playerId: 'P_FCT_24',
        playerName: 'ショルツ',
        number: 24,
        position: 'CB',
        isStarter: true,
        pitchX: 60.0,
        pitchY: 75.0,
      ),
      const PlayerContextItem(
        playerId: 'P_FCT_81',
        playerName: 'キム スンギュ',
        number: 81,
        position: 'GK',
        isStarter: true,
        pitchX: 50.0,
        pitchY: 90.0,
      ),
      const PlayerContextItem(
        playerId: 'P_FCT_71',
        playerName: '荒木 遼太郎',
        number: 71,
        position: 'OMF',
        isStarter: true,
        pitchX: 50.0,
        pitchY: 35.0,
      ),
      const PlayerContextItem(
        playerId: 'P_FCT_26',
        playerName: '長倉 幹樹',
        number: 26,
        position: 'CF',
        isStarter: true,
        pitchX: 50.0,
        pitchY: 15.0,
      ),
    ];

    return MatchAppContext(
      matchId: matchId,
      season: 2026,
      matchweek: 1,
      date: '2026-02-23',
      stadium: '味の素スタジアム',
      status: 'LIVE',
      homeTeam: TeamContextItem(
        teamId: 'FCT',
        teamName: 'FC東京',
        shortName: 'FC東京',
        score: 1,
        formation: '4-2-3-1',
        starters: tokyoStarters,
        bench: const [],
      ),
      awayTeam: const TeamContextItem(
        teamId: 'ZEL',
        teamName: '町田ゼルビア',
        shortName: '町田',
        score: 0,
        formation: '4-4-2',
        starters: [],
        bench: [],
      ),
      tacticalPreview: const {},
      liveStats: const {'home_score': 1, 'away_score': 0},
    );
  }
}

final matchTrackingProvider =
    NotifierProvider<MatchTrackingNotifier, MatchTrackingState>(
  MatchTrackingNotifier.new,
);
