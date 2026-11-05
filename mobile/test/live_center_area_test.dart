import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:mobile/models/action_models.dart';
import 'package:mobile/models/live_match_models.dart';
import 'package:mobile/models/match_models.dart';
import 'package:mobile/widgets/live/cards/player_detail_card.dart';
import 'package:mobile/widgets/live/cards/team_stats_card.dart';
import 'package:mobile/widgets/live/live_alert_banner.dart';
import 'package:mobile/widgets/live/live_center_area.dart';
import 'package:mobile/widgets/player_pin.dart';

void main() {
  group('Live Models Serialization Tests', () {
    test('LiveSnapshotData fromJson properly parses snapshot', () {
      final sample = MockLiveSnapshot.getSample(minute: 70);
      expect(sample.matchId, '20261031_OKA_FCT');
      expect(sample.elapsedMinute, 70);
      expect(sample.score.home, 1);
      expect(sample.score.away, 0);
      expect(sample.metrics.homeFieldTilt, 0.64);
      expect(sample.playerLiveStatus.containsKey('P_FCT_10'), isTrue);
      expect(sample.playerLiveStatus['P_FCT_10']?.status, 'faded');
      expect(sample.playerLiveStatus['P_FCT_26']?.status, 'overdrive');
      expect(sample.timelineAlert?.active, isTrue);
      expect(sample.latestAiTweet?.persona, 'tactical_geek');
      expect(sample.rawEvents.length, greaterThan(0));
    });
  });

  group('LiveCenterArea Widget Tests', () {
    testWidgets('LiveCenterArea renders tab header, alert banner and PageView',
        (tester) async {
      final sample = MockLiveSnapshot.getSample(minute: 65);
      final dummyActions = [
        const UserAction(
          id: 'act_1',
          matchId: 'm1',
          playerId: 'p1',
          teamId: 't1',
          actionType: 'good',
          matchMinute: 20,
          createdAt: '2026-11-06T00:00:00Z',
        ),
      ];

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SizedBox(
              height: 240,
              child: LiveCenterArea(
                snapshot: sample,
                userActions: dummyActions,
                homeTeamName: '岡山',
                awayTeamName: 'FC東京',
              ),
            ),
          ),
        ),
      );

      // Verify header and banner
      expect(find.byType(LiveAlertBanner), findsOneWidget);
      expect(find.text('⚠️ 警戒時間帯 (60〜75分)'), findsOneWidget);
      expect(find.text('チームスタッツ'), findsOneWidget);
      expect(find.byType(TeamStatsCard), findsOneWidget);

      // Swipe to page 2 (PlayerDetailCard)
      await tester.drag(find.byType(PageView), const Offset(-400, 0));
      await tester.pumpAndSettle();

      expect(find.text('選手詳細'), findsOneWidget);
      expect(find.byType(PlayerDetailCard), findsOneWidget);
    });

    testWidgets('PlayerDetailCard updates when player is double-tapped',
        (tester) async {
      final sample = MockLiveSnapshot.getSample(minute: 65);
      const testPlayer = PlayerContextItem(
        playerId: 'P_FCT_10',
        playerName: '佐藤 恵允',
        number: 10,
        position: 'RSH',
        isStarter: true,
        pitchX: 86.0,
        pitchY: 48.0,
      );

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SizedBox(
              height: 240,
              child: LiveCenterArea(
                snapshot: sample,
                userActions: const [],
                selectedPlayer: testPlayer,
                selectedPlayerScore: 3,
              ),
            ),
          ),
        ),
      );

      await tester.pumpAndSettle();

      // Should automatically jump to player detail page
      expect(find.byType(PlayerDetailCard), findsOneWidget);
      expect(find.text('#10 佐藤 恵允'), findsOneWidget);
      expect(find.text('RSH'), findsOneWidget);
      expect(find.text('ライブ観戦評価点: +3 pts'), findsOneWidget);
    });
  });

  group('PlayerPin Dynamic Effects Tests', () {
    testWidgets('PlayerPin opacity is 0.5 when status is faded (消えてる)',
        (tester) async {
      const p = PlayerContextItem(
        playerId: 'p1',
        playerName: 'テスト選手',
        number: 10,
        position: 'OM',
        isStarter: true,
        pitchX: 50.0,
        pitchY: 50.0,
      );

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: PlayerPin(
              player: p,
              teamId: 't1',
              liveStatus: 'faded',
              onAction: (a, c) {},
            ),
          ),
        ),
      );

      final opacityWidget = tester.widget<Opacity>(find.byType(Opacity));
      expect(opacityWidget.opacity, 0.50);
    });

    testWidgets('PlayerPin triggers onDoubleTap callback', (tester) async {
      bool doubleTapped = false;
      const p = PlayerContextItem(
        playerId: 'p1',
        playerName: 'テスト選手',
        number: 10,
        position: 'OM',
        isStarter: true,
        pitchX: 50.0,
        pitchY: 50.0,
      );

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: PlayerPin(
              player: p,
              teamId: 't1',
              onDoubleTap: () => doubleTapped = true,
              onAction: (a, c) {},
            ),
          ),
        ),
      );

      // Perform double tap gesture
      await tester.tap(find.byType(PlayerPin));
      await tester.pump(const Duration(milliseconds: 50));
      await tester.tap(find.byType(PlayerPin));
      await tester.pumpAndSettle();

      expect(doubleTapped, isTrue);
    });
  });
}
