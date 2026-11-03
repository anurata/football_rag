import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:path/path.dart' as p;
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import '../models/action_models.dart';

class LocalDbService {
  static final LocalDbService instance = LocalDbService._internal();
  LocalDbService._internal();

  Database? _db;

  Future<Database> get database async {
    if (_db != null) return _db!;
    _db = await _initDatabase();
    return _db!;
  }

  Future<Database> _initDatabase() async {
    if (!kIsWeb && (Platform.isWindows || Platform.isLinux)) {
      sqfliteFfiInit();
      databaseFactory = databaseFactoryFfi;
    }

    final dbPath = await getDatabasesPath();
    final path = p.join(dbPath, 'football_rag_mobile.db');

    return await openDatabase(
      path,
      version: 2,
      onCreate: (db, version) async {
        await db.execute('''
          CREATE TABLE local_actions (
            id TEXT PRIMARY KEY,
            match_id TEXT NOT NULL,
            player_id TEXT NOT NULL,
            player_name TEXT,
            team_id TEXT NOT NULL,
            action_type TEXT NOT NULL,
            match_minute INTEGER NOT NULL,
            play_category TEXT,
            note TEXT,
            bonus_points INTEGER DEFAULT 0,
            created_at TEXT,
            is_synced INTEGER DEFAULT 0
          );
        ''');
      },
      onUpgrade: (db, oldVersion, newVersion) async {
        if (oldVersion < 2) {
          try {
            await db.execute(
              'ALTER TABLE local_actions ADD COLUMN bonus_points INTEGER DEFAULT 0;',
            );
          } catch (_) {}
        }
      },
    );
  }

  Future<void> insertAction(UserAction action) async {
    final db = await database;
    await db.insert(
      'local_actions',
      action.toDbMap(),
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  Future<void> updateBonusPoints(String actionId, int bonusPoints) async {
    final db = await database;
    await db.update(
      'local_actions',
      {
        'bonus_points': bonusPoints,
        'is_synced': 0,
      },
      where: 'id = ?',
      whereArgs: [actionId],
    );
  }

  Future<void> deleteAction(String actionId) async {
    final db = await database;
    await db.delete(
      'local_actions',
      where: 'id = ?',
      whereArgs: [actionId],
    );
  }

  Future<List<UserAction>> getUnsyncedActions() async {
    final db = await database;
    final List<Map<String, dynamic>> maps = await db.query(
      'local_actions',
      where: 'is_synced = ?',
      whereArgs: [0],
    );
    return maps.map((m) => UserAction.fromJson(m)).toList();
  }

  Future<void> markActionsSynced(List<String> ids) async {
    if (ids.isEmpty) return;
    final db = await database;
    final batch = db.batch();
    for (final id in ids) {
      batch.update(
        'local_actions',
        {'is_synced': 1},
        where: 'id = ?',
        whereArgs: [id],
      );
    }
    await batch.commit(noResult: true);
  }

  Future<List<UserAction>> getActionsForMatch(
    String matchId, {
    int limit = 50,
  }) async {
    final db = await database;
    final List<Map<String, dynamic>> maps = await db.query(
      'local_actions',
      where: 'match_id = ?',
      whereArgs: [matchId],
      orderBy: 'created_at DESC',
      limit: limit,
    );
    return maps.map((m) => UserAction.fromJson(m)).toList();
  }
}
