import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'screens/match_tracking_screen.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(
    const ProviderScope(
      child: FootballRagApp(),
    ),
  );
}

class FootballRagApp extends StatelessWidget {
  const FootballRagApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'J-League Match Tracker',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: Colors.black,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF1B5E20),
          brightness: Brightness.dark,
        ),
        useMaterial3: true,
      ),
      home: const MatchTrackingScreen(
        matchId: '20261031_OKA_FCT',
      ),
    );
  }
}
