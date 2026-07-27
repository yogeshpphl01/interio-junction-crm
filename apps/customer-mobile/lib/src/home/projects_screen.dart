import 'package:flutter/material.dart';
import 'package:ij_core/ij_core.dart';

import '../services.dart';
import '../widgets.dart';

/// Home tab: the customer's project(s) and pipeline stage (contract §4.3).
class ProjectsTab extends StatelessWidget {
  const ProjectsTab({super.key});

  @override
  Widget build(BuildContext context) {
    return AsyncRefresh<List<ClientProject>>(
      load: Services.i.data.projects,
      onData: (projects, refresh) {
        if (projects.isEmpty) {
          return const EmptyState(
            icon: Icons.home_work_outlined,
            text: 'Your project details will appear here\nonce your journey begins.',
          );
        }
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [for (final p in projects) _ProjectCard(p)],
        );
      },
    );
  }
}

class _ProjectCard extends StatelessWidget {
  const _ProjectCard(this.p);
  final ClientProject p;

  Color get _stageColor {
    final hex = p.stageColor?.replaceFirst('#', '');
    if (hex == null || hex.length != 6) return const Color(0xFF7C9082);
    return Color(int.parse('FF$hex', radix: 16));
  }

  @override
  Widget build(BuildContext context) {
    final proj = p.project;
    return Card(
      margin: const EdgeInsets.only(bottom: 16),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            color: _stageColor.withOpacity(0.15),
            child: Row(children: [
              Icon(Icons.circle, size: 10, color: _stageColor),
              const SizedBox(width: 8),
              Text('Stage ${p.stage} · ${p.stageName}',
                  style: TextStyle(color: _stageColor, fontWeight: FontWeight.w600)),
            ]),
          ),
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(p.fullName ?? 'Your project',
                    style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
                if (p.bhkType != null || p.requirements != null) ...[
                  const SizedBox(height: 4),
                  Text([p.bhkType, p.requirements].whereType<String>().join(' · '),
                      style: const TextStyle(color: Colors.black54)),
                ],
                if (proj != null) ...[
                  const Divider(height: 24),
                  _row('Project', proj.projectCode ?? '—'),
                  _row('Contract value', inr(proj.contractValue)),
                  _row('Booking', proj.bookingPaid ? 'Paid ✓' : 'Pending'),
                  _row('In production', proj.inProduction ? 'Yes' : 'Not yet'),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _row(String k, String v) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 3),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(k, style: const TextStyle(color: Colors.black54)),
            Text(v, style: const TextStyle(fontWeight: FontWeight.w600)),
          ],
        ),
      );
}
