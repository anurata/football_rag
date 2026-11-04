import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/match_models.dart';

/// Modal bottom sheet for performing in-match player substitutions.
class SubstitutionModal extends StatefulWidget {
  final TeamContextItem team;
  final bool isHome;
  final Function(String outPlayerId, String inPlayerId) onConfirm;

  const SubstitutionModal({
    super.key,
    required this.team,
    required this.isHome,
    required this.onConfirm,
  });

  static Future<void> show({
    required BuildContext context,
    required TeamContextItem team,
    required bool isHome,
    required Function(String outPlayerId, String inPlayerId) onConfirm,
  }) {
    return showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: const Color(0xFF0F172A),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) => SubstitutionModal(
        team: team,
        isHome: isHome,
        onConfirm: onConfirm,
      ),
    );
  }

  @override
  State<SubstitutionModal> createState() => _SubstitutionModalState();
}

class _SubstitutionModalState extends State<SubstitutionModal> {
  String? _selectedOutId;
  String? _selectedInId;

  @override
  Widget build(BuildContext context) {
    final canConfirm = _selectedOutId != null && _selectedInId != null;

    return SafeArea(
      child: Container(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _buildHeader(),
            const SizedBox(height: 12),
            _buildSectionTitle('1. 退場選手 (OUT) を選択', Colors.redAccent),
            const SizedBox(height: 6),
            _buildStartersList(),
            const SizedBox(height: 14),
            _buildSectionTitle('2. 出場選手 (IN) を選択', Colors.greenAccent),
            const SizedBox(height: 6),
            _buildBenchList(),
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
        const Icon(Icons.swap_horiz, color: Colors.amberAccent, size: 20),
        const SizedBox(width: 8),
        Text(
          '選手交代 - ${widget.team.shortName}',
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

  Widget _buildSectionTitle(String title, Color color) {
    return Text(
      title,
      style: TextStyle(
        fontSize: 12,
        fontWeight: FontWeight.bold,
        color: color,
        letterSpacing: 0.3,
      ),
    );
  }

  Widget _buildStartersList() {
    return SizedBox(
      height: 38,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: widget.team.starters.length,
        separatorBuilder: (context, index) => const SizedBox(width: 6),
        itemBuilder: (context, index) {
          final p = widget.team.starters[index];
          final isSelected = p.playerId == _selectedOutId;
          return _buildPlayerChip(
            player: p,
            isSelected: isSelected,
            selectedColor: Colors.red[800]!,
            onTap: () {
              HapticFeedback.selectionClick();
              setState(() {
                _selectedOutId = p.playerId;
              });
            },
          );
        },
      ),
    );
  }

  Widget _buildBenchList() {
    return SizedBox(
      height: 38,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: widget.team.bench.length,
        separatorBuilder: (context, index) => const SizedBox(width: 6),
        itemBuilder: (context, index) {
          final p = widget.team.bench[index];
          final isSelected = p.playerId == _selectedInId;
          return _buildPlayerChip(
            player: p,
            isSelected: isSelected,
            selectedColor: Colors.green[800]!,
            onTap: () {
              HapticFeedback.selectionClick();
              setState(() {
                _selectedInId = p.playerId;
              });
            },
          );
        },
      ),
    );
  }

  Widget _buildPlayerChip({
    required PlayerContextItem player,
    required bool isSelected,
    required Color selectedColor,
    required VoidCallback onTap,
  }) {
    return ActionChip(
      padding: const EdgeInsets.symmetric(horizontal: 4),
      backgroundColor: isSelected ? selectedColor : const Color(0xFF1E293B),
      side: BorderSide(
        color: isSelected ? Colors.white : Colors.white24,
        width: isSelected ? 1.5 : 1,
      ),
      label: Text(
        '#${player.number} ${player.displayName}',
        style: TextStyle(
          fontSize: 11,
          fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
          color: Colors.white,
        ),
      ),
      onPressed: onTap,
    );
  }

  Widget _buildConfirmButton(bool canConfirm) {
    return SizedBox(
      width: double.infinity,
      height: 44,
      child: ElevatedButton(
        style: ElevatedButton.styleFrom(
          backgroundColor: canConfirm ? Colors.amber[700] : Colors.white12,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(10),
          ),
        ),
        onPressed: canConfirm
            ? () {
                HapticFeedback.mediumImpact();
                widget.onConfirm(_selectedOutId!, _selectedInId!);
                Navigator.pop(context);
              }
            : null,
        child: Text(
          canConfirm ? '選手交代を実行する' : 'OUT / IN選手を選択してください',
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
