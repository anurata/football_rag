import 'package:dio/dio.dart';
import '../models/action_models.dart';
import '../models/match_models.dart';

class ApiClient {
  final Dio _dio;
  String baseUrl;

  ApiClient({String? baseUrl})
      : baseUrl = baseUrl ?? 'http://127.0.0.1:8000',
        _dio = Dio(
          BaseOptions(
            baseUrl: baseUrl ?? 'http://127.0.0.1:8000',
            connectTimeout: const Duration(seconds: 4),
            receiveTimeout: const Duration(seconds: 4),
          ),
        );

  void updateBaseUrl(String newUrl) {
    baseUrl = newUrl;
    _dio.options.baseUrl = newUrl;
  }

  Future<MatchAppContext?> fetchMatchAppContext(String matchId) async {
    try {
      final response = await _dio.get('/api/matches/$matchId/app_context');
      if (response.statusCode == 200 && response.data != null) {
        return MatchAppContext.fromJson(
          response.data as Map<String, dynamic>,
        );
      }
    } catch (e) {
      // Offline or network error
    }
    return null;
  }

  Future<bool> syncActions(List<UserAction> actions) async {
    if (actions.isEmpty) return true;
    try {
      final payload = {
        'actions': actions.map((a) => a.toJson()).toList(),
      };
      final response = await _dio.post(
        '/api/sync/actions',
        data: payload,
      );
      if (response.statusCode == 200) {
        return true;
      }
    } catch (e) {
      // Offline fallback
    }
    return false;
  }

  Future<List<Map<String, dynamic>>> fetchRecentMatches() async {
    try {
      final response = await _dio.get('/api/matches/recent?limit=25');
      if (response.statusCode == 200 && response.data != null) {
        final list = response.data['matches'] as List<dynamic>? ?? [];
        return list.map((e) => e as Map<String, dynamic>).toList();
      }
    } catch (e) {
      // Offline fallback
    }
    return [];
  }
}
