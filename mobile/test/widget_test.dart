import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/models/action_models.dart';
import 'package:mobile/models/match_models.dart';
import 'package:mobile/widgets/player_pin.dart';

void main() {
  group('Model Serialization Tests', () {
    test('UserAction serialization and toDbMap', () {
      final action = UserAction(
        id: 'test_uuid_123',
        matchId: '2026_M01_FCT_ZEL',
        playerId: 'P_FCT_37',
        playerName: '小泉 慶',
        teamId: 'FCT',
        actionType: 'good',
        matchMinute: 23,
        playCategory: 'pass',
        note: 'ナイススルーパス',
        createdAt: '2026-11-03T16:00:00Z',
        isSynced: false,
      );

      final json = action.toJson();
      expect(json['id'], 'test_uuid_123');
      expect(json['action_type'], 'good');
      expect(json['match_minute'], 23);

      final dbMap = action.toDbMap();
      expect(dbMap['is_synced'], 0);
      expect(dbMap['player_name'], '小泉 慶');

      final reconstructed = UserAction.fromJson(dbMap);
      expect(reconstructed.id, action.id);
      expect(reconstructed.playerName, action.playerName);
      expect(reconstructed.isSynced, false);
    });

    test('MatchAppContext serialization', () {
      final ctx = MatchAppContext(
        matchId: '2026_M01_FCT_ZEL',
        season: 2026,
        matchweek: 1,
        date: '2026-02-23',
        stadium: '味の素スタジアム',
        status: 'LIVE',
        homeTeam: const TeamContextItem(
          teamId: 'FCT',
          teamName: 'FC東京',
          shortName: 'FC東京',
          score: 1,
          formation: '4-2-3-1',
          starters: [
            PlayerContextItem(
              playerId: 'P_FCT_37',
              playerName: '小泉 慶',
              number: 37,
              position: 'DMF',
              isStarter: true,
              pitchX: 45.0,
              pitchY: 55.0,
            ),
          ],
          bench: [],
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
        tacticalPreview: {'key': 'val'},
        liveStats: {'home_score': 1},
      );

      final json = ctx.toJson();
      final fromJson = MatchAppContext.fromJson(json);

      expect(fromJson.matchId, '2026_M01_FCT_ZEL');
      expect(fromJson.homeTeam.starters.length, 1);
      expect(fromJson.homeTeam.starters.first.playerName, '小泉 慶');
      expect(fromJson.homeTeam.starters.first.pitchX, 45.0);
    });
  });

  group('PlayerPin Widget Tests', () {
    testWidgets('PlayerPin renders without overflow at standard and 1.5x font scale', (
      WidgetTester tester,
    ) async {
      const player = PlayerContextItem(
        playerId: 'p_fct_24',
        playerName: 'アレクサンダー ショルツ',
        number: 24,
        position: 'CB',
        isStarter: true,
        pitchX: 50.0,
        pitchY: 70.0,
      );

      // Test with 1.5x font scale factor (simulates user large font setting)
      await tester.pumpWidget(
        MaterialApp(
          home: MediaQuery(
            data: const MediaQueryData(
              textScaler: TextScaler.linear(1.5),
            ),
            child: Scaffold(
              body: SizedBox(
                width: 82.0,
                height: 46.0,
                child: PlayerPin(
                  player: player,
                  teamId: 'FCT',
                  onAction: (actionType, category) {},
                ),
              ),
            ),
          ),
        ),
      );

      await tester.pumpAndSettle();

      // Verify no overflow exception was thrown and player elements are visible
      expect(find.text('24'), findsOneWidget);
      expect(find.text('CB'), findsOneWidget);
      expect(find.text('アレクサンダー ショルツ'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  });
}
