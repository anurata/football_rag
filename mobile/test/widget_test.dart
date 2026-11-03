import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/models/action_models.dart';
import 'package:mobile/models/match_models.dart';
import 'package:mobile/widgets/action_ticker.dart';
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
        bonusPoints: 2,
        createdAt: '2026-11-03T16:00:00Z',
        isSynced: false,
      );

      expect(action.netPoints, 3); // 1 + 2

      final json = action.toJson();
      expect(json['id'], 'test_uuid_123');
      expect(json['action_type'], 'good');
      expect(json['match_minute'], 23);
      expect(json['bonus_points'], 2);

      final dbMap = action.toDbMap();
      expect(dbMap['is_synced'], 0);
      expect(dbMap['player_name'], '小泉 慶');
      expect(dbMap['bonus_points'], 2);

      final reconstructed = UserAction.fromJson(dbMap);
      expect(reconstructed.id, action.id);
      expect(reconstructed.playerName, action.playerName);
      expect(reconstructed.bonusPoints, 2);
      expect(reconstructed.netPoints, 3);
      expect(reconstructed.positivePoints, 3);
      expect(reconstructed.negativePoints, 0);

      final badAction = UserAction(
        id: 'bad_1',
        matchId: '20261031_OKA_FCT',
        playerId: 'p1',
        teamId: 'OKA',
        actionType: 'bad',
        matchMinute: 15,
        bonusPoints: 0,
        createdAt: '2026-11-04T00:00:00Z',
      );
      expect(badAction.positivePoints, 0);
      expect(badAction.negativePoints, 1);
      expect(badAction.netPoints, -1);
    });

    test('PlayerScoreSummary calculation and serialization', () {
      const summary = PlayerScoreSummary(
        playerId: 'p_oka_10',
        positivePoints: 7,
        negativePoints: 2,
      );
      expect(summary.netScore, 5);
      final json = summary.toJson();
      expect(json['positive_points'], 7);
      expect(json['negative_points'], 2);
      expect(json['net_score'], 5);

      final fromJson = PlayerScoreSummary.fromJson(json);
      expect(fromJson.playerId, 'p_oka_10');
      expect(fromJson.positivePoints, 7);
      expect(fromJson.negativePoints, 2);
      expect(fromJson.netScore, 5);
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

      // Verify no overflow exception was thrown and player elements are visible with short name
      expect(find.text('24'), findsOneWidget);
      expect(find.text('CB'), findsOneWidget);
      expect(find.text('ショルツ'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('PlayerPin number circle has uniform dimensions for 1-digit and 2-digit numbers', (
      WidgetTester tester,
    ) async {
      const p1 = PlayerContextItem(
        playerId: 'p1',
        playerName: '稲村 隼翔',
        number: 4,
        position: 'LCB',
        isStarter: true,
        pitchX: 38.0,
        pitchY: 66.0,
      );
      const p2 = PlayerContextItem(
        playerId: 'p2',
        playerName: 'ルカオ',
        number: 99,
        position: 'CF',
        isStarter: true,
        pitchX: 50.0,
        pitchY: 16.0,
      );

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Row(
              children: [
                SizedBox(
                  width: 82.0,
                  height: 46.0,
                  child: PlayerPin(
                    player: p1,
                    teamId: 'FCT',
                    isHome: true,
                    onAction: (a, c) {},
                  ),
                ),
                SizedBox(
                  width: 82.0,
                  height: 46.0,
                  child: PlayerPin(
                    player: p2,
                    teamId: 'OKA',
                    isHome: false,
                    onAction: (a, c) {},
                  ),
                ),
              ],
            ),
          ),
        ),
      );

      await tester.pumpAndSettle();

      // Find the circular badge containers
      final badges = tester.widgetList<Container>(
        find.byWidgetPredicate(
          (w) =>
              w is Container &&
              w.constraints?.minWidth == 18 &&
              w.constraints?.minHeight == 18,
        ),
      );

      // Verify both 1-digit and 2-digit badges have fixed 18x18 size
      expect(badges.length, 2);
      for (final b in badges) {
        expect(b.constraints?.maxWidth, 18);
        expect(b.constraints?.maxHeight, 18);
      }
    });

    testWidgets('PlayerPin renders Home in fagiano red and Away in white kit', (
      WidgetTester tester,
    ) async {
      const pHome = PlayerContextItem(
        playerId: 'p_home',
        playerName: '濱田 太郎',
        number: 52,
        position: 'GK',
        isStarter: true,
        pitchX: 50.0,
        pitchY: 88.0,
      );
      const pAway = PlayerContextItem(
        playerId: 'p_away',
        playerName: 'キム スンギュ',
        number: 81,
        position: 'GK',
        isStarter: true,
        pitchX: 50.0,
        pitchY: 89.0,
      );

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Column(
              children: [
                SizedBox(
                  width: 82.0,
                  height: 46.0,
                  child: PlayerPin(
                    player: pHome,
                    teamId: 'OKA',
                    isHome: true,
                    onAction: (a, c) {},
                  ),
                ),
                SizedBox(
                  width: 82.0,
                  height: 46.0,
                  child: PlayerPin(
                    player: pAway,
                    teamId: 'FCT',
                    isHome: false,
                    onAction: (a, c) {},
                  ),
                ),
              ],
            ),
          ),
        ),
      );

      await tester.pumpAndSettle();

      // Home pin card has 0xFF7D1B2D color
      final animatedContainers = tester.widgetList<AnimatedContainer>(
        find.byType(AnimatedContainer),
      );
      expect(animatedContainers.length, 2);

      final homeDec = animatedContainers.first.decoration as BoxDecoration;
      expect(homeDec.color, const Color(0xFF7D1B2D));

      final awayDec = animatedContainers.last.decoration as BoxDecoration;
      expect(awayDec.color, Colors.white);
    });

    testWidgets('PlayerPin number circle color reflects gradient from -5 to +15 pts', (
      WidgetTester tester,
    ) async {
      const p = PlayerContextItem(
        playerId: 'p1',
        playerName: 'ルカオ',
        number: 99,
        position: 'CF',
        isStarter: true,
        pitchX: 50.0,
        pitchY: 16.0,
      );

      // 1. Min score (-5 pts): deep crimson red (0xFF991B1B)
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SizedBox(
              width: 82.0,
              height: 46.0,
              child: PlayerPin(
                player: p,
                teamId: 'OKA',
                isHome: true,
                score: -5,
                onAction: (a, c) {},
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      var badgeFinder = find.byWidgetPredicate(
        (w) =>
            w is Container &&
            w.constraints?.minWidth == 18 &&
            w.decoration is BoxDecoration &&
            (w.decoration as BoxDecoration).shape == BoxShape.circle,
      );
      expect(badgeFinder, findsOneWidget);
      var badgeBox = tester.widget<Container>(badgeFinder).decoration as BoxDecoration;
      expect(badgeBox.color, const Color(0xFF991B1B));
      expect(find.text('-5'), findsOneWidget);

      // 2. Max score (+15 pts): shining gold (0xFFFFD700)
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SizedBox(
              width: 82.0,
              height: 46.0,
              child: PlayerPin(
                player: p,
                teamId: 'OKA',
                isHome: true,
                score: 15,
                onAction: (a, c) {},
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      badgeBox = tester.widget<Container>(badgeFinder).decoration as BoxDecoration;
      expect(badgeBox.color, const Color(0xFFFFD700));
      expect(find.text('+15'), findsOneWidget);
    });
  });

  group('ActionTicker Widget Tests', () {
    testWidgets('ActionTicker displays stopwatch, handles running state and 45min orange background', (
      WidgetTester tester,
    ) async {
      bool timerToggled = false;
      bool minuteIncremented = false;
      bool minuteDecremented = false;
      bool timerLongPressed = false;

      // 1. Stopped state before 45 minutes
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ActionTicker(
              currentMinute: 20,
              formattedTime: '20:15',
              isTimerRunning: false,
              isOver45Minutes: false,
              recentActions: const [],
              syncStatus: '同期済み',
              onIncrementMinute: () => minuteIncremented = true,
              onDecrementMinute: () => minuteDecremented = true,
              onToggleTimer: () => timerToggled = true,
              onLongPressTimer: () => timerLongPressed = true,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('20:15'), findsOneWidget);
      expect(find.byIcon(Icons.remove), findsOneWidget);
      expect(find.byIcon(Icons.add), findsOneWidget);
      expect(find.byIcon(Icons.play_arrow), findsOneWidget);

      // Tap + and -
      await tester.tap(find.byIcon(Icons.add));
      await tester.pump();
      expect(minuteIncremented, isTrue);

      await tester.tap(find.byIcon(Icons.remove));
      await tester.pump();
      expect(minuteDecremented, isTrue);

      // Long press timer
      await tester.longPress(find.text('20:15'));
      await tester.pump();
      expect(timerLongPressed, isTrue);

      // 2. Running state after 45 minutes (Orange background)
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ActionTicker(
              currentMinute: 48,
              formattedTime: '48:30',
              isTimerRunning: true,
              isOver45Minutes: true,
              recentActions: const [],
              syncStatus: '同期済み',
              onIncrementMinute: () {},
              onDecrementMinute: () {},
              onToggleTimer: () => timerToggled = true,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('48:30'), findsOneWidget);
      expect(find.byIcon(Icons.pause), findsOneWidget);
      // Minus and plus buttons should be hidden while running
      expect(find.byIcon(Icons.remove), findsNothing);
      expect(find.byIcon(Icons.add), findsNothing);

      // Verify orange background Container
      final timerContainerFinder = find.byWidgetPredicate(
        (w) =>
            w is AnimatedContainer &&
            w.decoration is BoxDecoration &&
            (w.decoration as BoxDecoration).color == const Color(0xFFEA580C),
      );
      expect(timerContainerFinder, findsOneWidget);

      // Tap to toggle timer (pause)
      await tester.tap(find.text('48:30'));
      await tester.pump();
      expect(timerToggled, isTrue);
    });
  });
}
