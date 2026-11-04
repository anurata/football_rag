import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/match_models.dart';

/// Modal bottom sheet for swapping positions between two starters on the pitch.
class PositionSwapModal extends StatefulWidget {
  final TeamContextItem team;
  final bool isHome;
  final Function(String player1Id, String player2Id) onConfirm;

  const PositionSwapModal({
    super.key,
    required this.team,
    required this.isHome,
    required this.onConfirm,
  });

  static Future<void> show({
    required BuildContext context,
    required TeamContextItem team,
    required bool isHome,
    required Function(String player1Id, String player2Id) onConfirm,
  }) {
    return showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: const Color(0xFF0F172A),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) => PositionSwapModal(
        team: team,
        isHome: isHome,
        onConfirm: onConfirm,
      ),
    );
  }

  @override
  State<PositionSwapModal> createState() => _PositionSwapModalState();
}

class _PositionSwapModalState extends State<PositionSwapModal> {
  String? _selectedPlayer1Id;
  String? _selectedPlayer2Id;

  @override
  Widget build(BuildContext context) {
    final canConfirm = _selectedPlayer1Id != null &&
        _selectedPlayer2Id != null &&
        _selectedPlayer1Id != _selectedPlayer2Id;

    return SafeArea(
      child: Container(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _buildHeader(),
            const SizedBox(height: 10),
            _buildDescriptionText(),
            const SizedBox(height: 12),
            _buildStartersWrap(),
            const SizedBox(height: 16),
            _buildConfirmButton(canConfirm),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader() {
    return Row(
      children: [
        const Icon(Icons.sync_alt, color: Colors.cyanAccent, size: 20),
        const SizedBox(width: 8),
        Text(
          'ポジション入替 - ${widget.team.shortName}',
          style: const TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.bold,
            color: Colors.white,
          ),
        ),
        const Spacer(),
        IconButton(
          visualDensity: VisualDensity.compact,
          icon: const Icon(Icons.close, color: Colors.white54, size: 20),
          onPressed: () => Navigator.pop(context),
        ),
      ],
    );
  }

  Widget _buildDescriptionText() {
    return const Text(
      'ピッチ上のスタメンから入れ替えたい選手を2名選択してください。',
      style: TextStyle(
        fontSize: 11,
        color: Colors.white60,
      ),
    );
  }

  Widget _buildStartersWrap() {
    return Wrap(
      spacing: 6,
      runSpacing: 6,
      children: widget.team.starters.map((player) {
        final isP1 = player.playerId == _selectedPlayer1Id;
        final isP2 = player.playerId == _selectedPlayer2Id;
        final isSelected = isP1 || isP2;

        final badgeText = isP1 ? ' (A)' : (isP2 ? ' (B)' : '');
        final bgColor = isP1
            ? const Color(0xFF0369A1) // Sky 700
            : (isP2 ? const Color(0xFF0D9488) : const Color(0xFF1E293B)); // Teal 600

        return ActionChip(
          padding: const EdgeInsets.symmetric(horizontal: 4),
          backgroundColor: isSelected ? bgColor : const Color(0xFF1E293B),
          side: BorderSide(
            color: isSelected ? Colors.cyanAccent : Colors.white24,
            width: isSelected ? 1.5 : 1,
          ),
          label: Text(
            '#${player.number} ${player.displayName} [${player.position}]$badgeText',
            style: TextStyle(
              fontSize: 11,
              fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
              color: Colors.white,
            ),
          ),
          onPressed: () {
            HapticFeedback.selectionClick();
            setState(() {
              if (isP1) {
                _selectedPlayer1Id = null;
              } else if (isP2) {
                _selectedPlayer2Id = null;
              } else if (_selectedPlayer1Id == null) {
                _selectedPlayer1Id = player.playerId;
              } else if (_selectedPlayer2Id == null) {
                _selectedPlayer2Id = player.playerId;
              } else {
                // If both already selected, replace player 2
                _selectedPlayer2Id = player.playerId;
              }
            });
          },
        );
      }).toList(),
    );
  }

  Widget _buildConfirmButton(bool canConfirm) {
    return SizedBox(
      width: double.infinity,
      height: 44,
      child: ElevatedButton(
        style: ElevatedButton.styleFrom(
          backgroundColor: canConfirm ? Colors.cyan[600] : Colors.white12,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(10),
          ),
        ),
        onPressed: canConfirm
            ? () {
                HapticFeedback.mediumImpact();
                widget.onConfirm(_selectedPlayer1Id!, _selectedPlayer2Id!);
                Navigator.pop(context);
              }
            : null,
        child: Text(
          canConfirm ? 'ポジション入替を実行する' : '2名の選手を選択してください',
          style: TextStyle(
            fontSize: 13,
            fontWeight: FontWeight.bold,
            color: canConfirm ? Colors.black : Colors.white38,
          ),
        ),
      ),
    );
  }
}
