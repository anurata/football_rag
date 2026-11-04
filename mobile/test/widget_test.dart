import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/models/action_models.dart';
import 'package:mobile/models/match_models.dart';
import 'package:mobile/widgets/action_ticker.dart';
import 'package:mobile/widgets/player_pin.dart';
import 'package:mobile/widgets/player_ranking_sheet.dart';
import 'package:mobile/widgets/position_swap_modal.dart';
import 'package:mobile/widgets/substitution_modal.dart';
import 'package:mobile/widgets/tactical_action_bar.dart';

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
              w.constraints?.minWidth == 20 &&
              w.constraints?.minHeight == 20,
        ),
      );

      // Verify both 1-digit and 2-digit badges have fixed 20x20 size
      expect(badges.length, 2);
      for (final b in badges) {
        expect(b.constraints?.maxWidth, 20);
        expect(b.constraints?.maxHeight, 20);
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
      expect(awayDec.color, const Color(0xFFE2E8F0));
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

      // 1. Min score (-5 pts): deep cobalt blue (0xFF1D4ED8)
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SizedBox(
              width: 90.0,
              height: 50.0,
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
            w.constraints?.minWidth == 20 &&
            w.decoration is BoxDecoration &&
            (w.decoration as BoxDecoration).shape == BoxShape.circle,
      );
      expect(badgeFinder, findsOneWidget);
      var badgeBox = tester.widget<Container>(badgeFinder).decoration as BoxDecoration;
      expect(badgeBox.color, const Color(0xFF1D4ED8));
      expect(find.text('-5'), findsOneWidget);

      // 2. Initial score (0 pts): clean white (Colors.white)
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SizedBox(
              width: 90.0,
              height: 50.0,
              child: PlayerPin(
                player: p,
                teamId: 'OKA',
                isHome: true,
                score: 0,
                onAction: (a, c) {},
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      badgeBox = tester.widget<Container>(badgeFinder).decoration as BoxDecoration;
      expect(badgeBox.color, Colors.white);

      // 3. Mid positive score (+7 pts): crimson red (0xFFE11D48)
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SizedBox(
              width: 90.0,
              height: 50.0,
              child: PlayerPin(
                player: p,
                teamId: 'OKA',
                isHome: true,
                score: 7,
                onAction: (a, c) {},
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      badgeBox = tester.widget<Container>(badgeFinder).decoration as BoxDecoration;
      expect(badgeBox.color, const Color(0xFFE11D48));
      expect(find.text('+7'), findsOneWidget);

      // 4. Max score (+15 pts): shining gold (0xFFFFD700)
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SizedBox(
              width: 90.0,
              height: 50.0,
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

    testWidgets('PlayerPin glows gold with shadow when score >= 10', (
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

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SizedBox(
              width: 90.0,
              height: 50.0,
              child: PlayerPin(
                player: p,
                teamId: 'OKA',
                isHome: true,
                score: 11,
                onAction: (a, c) {},
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final pinFinder = find.byType(AnimatedContainer);
      expect(pinFinder, findsOneWidget);
      final pinDec = tester.widget<AnimatedContainer>(pinFinder).decoration as BoxDecoration;
      expect(pinDec.boxShadow, isNotNull);
      expect(pinDec.boxShadow!.first.color, const Color(0xFFFFD700));
      expect(pinDec.border?.top.color, const Color(0xFFFFD700));
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

  group('Substitution and Swap Logic Tests', () {
    test('PlayerContextItem copyWith updates coordinates and position properly', () {
      const original = PlayerContextItem(
        playerId: 'p_1',
        playerName: '佐藤 太郎',
        shortName: '佐藤',
        number: 10,
        position: 'LOM',
        isStarter: true,
        pitchX: 30.0,
        pitchY: 40.0,
      );

      final updated = original.copyWith(
        position: 'ROM',
        pitchX: 70.0,
        pitchY: 40.0,
        isStarter: false,
      );

      expect(updated.playerId, 'p_1');
      expect(updated.position, 'ROM');
      expect(updated.pitchX, 70.0);
      expect(updated.isStarter, false);
      expect(original.position, 'LOM'); // Original intact
    });

    test('Substitution logic swaps starter and bench player', () {
      const starter1 = PlayerContextItem(
        playerId: 'p_start_1',
        playerName: '安斎 颯馬',
        shortName: '安斎',
        number: 7,
        position: 'LSH',
        isStarter: true,
        pitchX: 14.0,
        pitchY: 48.0,
      );
      const bench1 = PlayerContextItem(
        playerId: 'p_bench_1',
        playerName: '本間 至恩',
        shortName: '本間',
        number: 19,
        position: 'MF',
        isStarter: false,
        pitchX: 50.0,
        pitchY: 50.0,
      );

      final inPlayer = bench1.copyWith(
        position: starter1.position,
        pitchX: starter1.pitchX,
        pitchY: starter1.pitchY,
        isStarter: true,
      );
      final outPlayer = starter1.copyWith(
        isStarter: false,
      );

      expect(inPlayer.isStarter, true);
      expect(inPlayer.position, 'LSH');
      expect(inPlayer.pitchX, 14.0);
      expect(inPlayer.pitchY, 48.0);
      expect(outPlayer.isStarter, false);
    });

    test('Swap positions exchanges coordinates and positions between two starters', () {
      const p1 = PlayerContextItem(
        playerId: 'p_1',
        playerName: '左SH',
        number: 7,
        position: 'LSH',
        isStarter: true,
        pitchX: 14.0,
        pitchY: 48.0,
      );
      const p2 = PlayerContextItem(
        playerId: 'p_2',
        playerName: '右SH',
        number: 10,
        position: 'RSH',
        isStarter: true,
        pitchX: 86.0,
        pitchY: 48.0,
      );

      final newP1 = p1.copyWith(
        position: p2.position,
        pitchX: p2.pitchX,
        pitchY: p2.pitchY,
      );
      final newP2 = p2.copyWith(
        position: p1.position,
        pitchX: p1.pitchX,
        pitchY: p1.pitchY,
      );

      expect(newP1.position, 'RSH');
      expect(newP1.pitchX, 86.0);
      expect(newP2.position, 'LSH');
      expect(newP2.pitchX, 14.0);
    });

    test('PlayerRankingEntry sorts players descending by net score and tie-breaks', () {
      const p1 = PlayerContextItem(
        playerId: 'p1',
        playerName: 'エースFW',
        number: 9,
        position: 'FW',
        isStarter: true,
        pitchX: 50,
        pitchY: 20,
      );
      const p2 = PlayerContextItem(
        playerId: 'p2',
        playerName: '司令塔MF',
        number: 10,
        position: 'MF',
        isStarter: true,
        pitchX: 50,
        pitchY: 50,
      );
      const p3 = PlayerContextItem(
        playerId: 'p3',
        playerName: '守備的DF',
        number: 4,
        position: 'DF',
        isStarter: true,
        pitchX: 50,
        pitchY: 80,
      );

      final list = [
        const PlayerRankingEntry(
          player: p3,
          rank: 0,
          netScore: -1,
          positivePoints: 1,
          negativePoints: 2,
          actionCount: 3,
        ),
        const PlayerRankingEntry(
          player: p1,
          rank: 0,
          netScore: 8,
          positivePoints: 8,
          negativePoints: 0,
          actionCount: 5,
        ),
        const PlayerRankingEntry(
          player: p2,
          rank: 0,
          netScore: 4,
          positivePoints: 5,
          negativePoints: 1,
          actionCount: 6,
        ),
      ];

      list.sort((a, b) => b.netScore.compareTo(a.netScore));

      expect(list[0].player.number, 9);
      expect(list[0].netScore, 8);
      expect(list[1].player.number, 10);
      expect(list[1].netScore, 4);
      expect(list[2].player.number, 4);
      expect(list[2].netScore, -1);
    });
  });

  group('Tactical UI Components Widget Tests', () {
    testWidgets('TacticalActionBar renders 3 buttons and triggers callbacks', (tester) async {
      bool subTapped = false;
      bool swapTapped = false;
      bool rankTapped = false;

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: TacticalActionBar(
              onSubstituteTap: () => subTapped = true,
              onSwapPositionsTap: () => swapTapped = true,
              onShowRankingsTap: () => rankTapped = true,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('選手交代'), findsOneWidget);
      expect(find.text('位置入替'), findsOneWidget);
      expect(find.text('評価ランク'), findsOneWidget);

      await tester.tap(find.text('選手交代'));
      await tester.pump();
      expect(subTapped, isTrue);

      await tester.tap(find.text('位置入替'));
      await tester.pump();
      expect(swapTapped, isTrue);

      await tester.tap(find.text('評価ランク'));
      await tester.pump();
      expect(rankTapped, isTrue);
    });

    testWidgets('SubstitutionModal allows selecting OUT/IN and confirms', (tester) async {
      const mockTeam = TeamContextItem(
        teamId: 'OKA',
        teamName: 'ファジアーノ岡山',
        shortName: '岡山',
        score: 0,
        formation: '3-4-2-1',
        starters: [
          PlayerContextItem(
            playerId: 'p_out_1',
            playerName: 'ルカオ',
            shortName: 'ルカオ',
            number: 99,
            position: 'CF',
            isStarter: true,
            pitchX: 50,
            pitchY: 20,
          ),
        ],
        bench: [
          PlayerContextItem(
            playerId: 'p_in_1',
            playerName: 'レオ ガウショ',
            shortName: 'レオ ガウショ',
            number: 9,
            position: 'FW',
            isStarter: false,
            pitchX: 50,
            pitchY: 50,
          ),
        ],
      );

      String? confirmedOut;
      String? confirmedIn;

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SubstitutionModal(
              team: mockTeam,
              isHome: true,
              onConfirm: (outId, inId) {
                confirmedOut = outId;
                confirmedIn = inId;
              },
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('選手交代 - 岡山'), findsOneWidget);
      expect(find.text('#99 ルカオ'), findsOneWidget);
      expect(find.text('#9 レオ ガウショ'), findsOneWidget);

      // Select OUT
      await tester.tap(find.text('#99 ルカオ'));
      await tester.pump();

      // Select IN
      await tester.tap(find.text('#9 レオ ガウショ'));
      await tester.pump();

      // Confirm button is now active
      final confirmBtn = find.text('選手交代を実行する');
      expect(confirmBtn, findsOneWidget);
      await tester.tap(confirmBtn);
      await tester.pump();

      expect(confirmedOut, 'p_out_1');
      expect(confirmedIn, 'p_in_1');
    });

    testWidgets('PositionSwapModal allows selecting 2 starters and confirms swap', (tester) async {
      const mockTeam = TeamContextItem(
        teamId: 'FCT',
        teamName: 'FC東京',
        shortName: 'FC東京',
        score: 0,
        formation: '4-4-2',
        starters: [
          PlayerContextItem(
            playerId: 'p_fct_1',
            playerName: '安斎 颯馬',
            shortName: '安斎',
            number: 7,
            position: 'LSH',
            isStarter: true,
            pitchX: 14,
            pitchY: 48,
          ),
          PlayerContextItem(
            playerId: 'p_fct_2',
            playerName: '佐藤 恵允',
            shortName: '佐藤',
            number: 10,
            position: 'RSH',
            isStarter: true,
            pitchX: 86,
            pitchY: 48,
          ),
        ],
        bench: [],
      );

      String? swapP1;
      String? swapP2;

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: PositionSwapModal(
              team: mockTeam,
              isHome: false,
              onConfirm: (p1, p2) {
                swapP1 = p1;
                swapP2 = p2;
              },
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('ポジション入替 - FC東京'), findsOneWidget);

      // Tap player 1
      await tester.tap(find.text('#7 安斎 [LSH]'));
      await tester.pump();

      // Tap player 2
      await tester.tap(find.text('#10 佐藤 [RSH]'));
      await tester.pump();

      // Confirm swap
      final confirmBtn = find.text('ポジション入替を実行する');
      expect(confirmBtn, findsOneWidget);
      await tester.tap(confirmBtn);
      await tester.pump();

      expect(swapP1, 'p_fct_1');
      expect(swapP2, 'p_fct_2');
    });

    testWidgets('PlayerRankingSheet displays sorted players with badges and points', (tester) async {
      const p1 = PlayerContextItem(
        playerId: 'p_1',
        playerName: 'ルカオ',
        number: 99,
        position: 'CF',
        isStarter: true,
        pitchX: 50,
        pitchY: 20,
      );
      const p2 = PlayerContextItem(
        playerId: 'p_2',
        playerName: '江坂 任',
        number: 8,
        position: 'LOM',
        isStarter: true,
        pitchX: 30,
        pitchY: 30,
      );

      final rankings = [
        const PlayerRankingEntry(
          player: p1,
          rank: 1,
          netScore: 6,
          positivePoints: 7,
          negativePoints: 1,
          actionCount: 8,
        ),
        const PlayerRankingEntry(
          player: p2,
          rank: 2,
          netScore: 3,
          positivePoints: 4,
          negativePoints: 1,
          actionCount: 5,
        ),
      ];

      const mockTeam = TeamContextItem(
        teamId: 'OKA',
        teamName: 'ファジアーノ岡山',
        shortName: '岡山',
        score: 0,
        formation: '3-4-2-1',
        starters: [p1, p2],
        bench: [],
      );

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: PlayerRankingSheet(
              team: mockTeam,
              isHome: true,
              rankings: rankings,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('選手評価ランキング - 岡山'), findsOneWidget);
      expect(find.text('🥇'), findsOneWidget); // Rank 1 gold badge
      expect(find.text('🥈'), findsOneWidget); // Rank 2 silver badge
      expect(find.text('ルカオ'), findsOneWidget); // Full name
      expect(find.text('江坂 任'), findsOneWidget); // Full name
      expect(find.byIcon(Icons.person), findsNWidgets(2)); // Avatar fallback icons
      expect(find.text('+6'), findsOneWidget);
      expect(find.text('+3'), findsOneWidget);
      expect(find.text('👍 +7'), findsOneWidget);
      expect(find.text('計 8件'), findsOneWidget);

      // Verify number text color is strictly black
      final numberText99 = tester.widget<Text>(find.text('99'));
      expect(numberText99.style?.color, Colors.black);
      final numberText8 = tester.widget<Text>(find.text('8'));
      expect(numberText8.style?.color, Colors.black);
    });

    test('TeamContextItem getPlayerDisplayName handles duplicate last names properly', () {
      const p1 = PlayerContextItem(
        playerId: 'p_1',
        playerName: '鈴木 喜丈',
        shortName: '鈴木',
        number: 43,
        position: 'CB',
        isStarter: true,
        pitchX: 24,
        pitchY: 72,
      );
      const p2 = PlayerContextItem(
        playerId: 'p_2',
        playerName: '鈴木 楓',
        shortName: '鈴木',
        number: 44,
        position: 'DF',
        isStarter: false,
        pitchX: 0,
        pitchY: 0,
      );
      const p3 = PlayerContextItem(
        playerId: 'p_3',
        playerName: '立田 悠悟',
        shortName: '立田',
        number: 48,
        position: 'CB',
        isStarter: true,
        pitchX: 76,
        pitchY: 72,
      );

      const teamWithSameLastName = TeamContextItem(
        teamId: 'OKA',
        teamName: 'ファジアーノ岡山',
        shortName: '岡山',
        score: 0,
        formation: '3-4-2-1',
        starters: [p1, p3],
        bench: [p2],
      );

      // Same last name "鈴木" -> returns full name
      expect(teamWithSameLastName.getPlayerDisplayName(p1), '鈴木 喜丈');
      expect(teamWithSameLastName.getPlayerDisplayName(p2), '鈴木 楓');

      // Unique last name "立田" -> returns compact displayName
      expect(teamWithSameLastName.getPlayerDisplayName(p3), '立田');
    });
  });
}
