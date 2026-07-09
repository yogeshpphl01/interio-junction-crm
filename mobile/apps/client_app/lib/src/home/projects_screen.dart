import 'package:flutter/material.dart';
import 'package:ij_core/ij_core.dart';

import '../services.dart';
import '../auth/otp_login_screen.dart';

/// The customer's home: their project(s) and where each one is in the pipeline
/// (contract §4.3). Pull-to-refresh; tap a card to drill into estimates/designs
/// /payments (those screens are the next to build against the contract).
class ProjectsScreen extends StatefulWidget {
  const ProjectsScreen({super.key});

  @override
  State<ProjectsScreen> createState() => _ProjectsScreenState();
}

class _ProjectsScreenState extends State<ProjectsScreen> {
  late Future<List<ClientProject>> _future;

  @override
  void initState() {
    super.initState();
    _future = Services.i.data.projects();
  }

  Future<void> _refresh() async {
    final next = Services.i.data.projects();
    setState(() => _future = next);
    await next;
  }

  Future<void> _logout() async {
    await Services.i.auth.logout();
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const OtpLoginScreen()),
      (_) => false,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('My Project'),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            tooltip: 'Sign out',
            onPressed: _logout,
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: FutureBuilder<List<ClientProject>>(
          future: _future,
          builder: (context, snap) {
            if (snap.connectionState == ConnectionState.waiting) {
              return const Center(child: CircularProgressIndicator());
            }
            if (snap.hasError) {
              return _Message(
                icon: Icons.error_outline,
                text: 'Could not load your project.\n${snap.error}',
                onRetry: _refresh,
              );
            }
            final projects = snap.data ?? const [];
            if (projects.isEmpty) {
              return const _Message(
                icon: Icons.home_work_outlined,
                text: 'Your project details will appear here\nonce your journey begins.',
              );
            }
            return ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: projects.length,
              itemBuilder: (context, i) => _ProjectCard(projects[i]),
            );
          },
        ),
      ),
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
            child: Row(
              children: [
                Icon(Icons.circle, size: 10, color: _stageColor),
                const SizedBox(width: 8),
                Text('Stage ${p.stage} · ${p.stageName}',
                    style: TextStyle(color: _stageColor, fontWeight: FontWeight.w600)),
              ],
            ),
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
                  _row('Contract value',
                      proj.contractValue == null ? '—' : '₹${proj.contractValue}'),
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

class _Message extends StatelessWidget {
  const _Message({required this.icon, required this.text, this.onRetry});
  final IconData icon;
  final String text;
  final Future<void> Function()? onRetry;

  @override
  Widget build(BuildContext context) {
    // Wrapped in a scroll view so RefreshIndicator still works when empty.
    return ListView(
      children: [
        const SizedBox(height: 120),
        Icon(icon, size: 56, color: Colors.black26),
        const SizedBox(height: 16),
        Text(text, textAlign: TextAlign.center, style: const TextStyle(color: Colors.black54)),
        if (onRetry != null) ...[
          const SizedBox(height: 16),
          Center(child: FilledButton.tonal(onPressed: onRetry, child: const Text('Retry'))),
        ],
      ],
    );
  }
}
