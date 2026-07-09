import 'package:flutter/material.dart';
import 'package:ij_core/ij_core.dart';

import '../services.dart';
import '../auth/login_screen.dart';

/// The employee home: a role-aware set of "things to act on" buckets
/// (contract §5.2). Only buckets the signed-in user is permitted to see are
/// returned by the API, so this UI is automatically correct for every role.
class WorklistScreen extends StatefulWidget {
  const WorklistScreen({super.key});

  @override
  State<WorklistScreen> createState() => _WorklistScreenState();
}

class _WorklistScreenState extends State<WorklistScreen> {
  late Future<List<WorklistBucket>> _future;

  @override
  void initState() {
    super.initState();
    _future = Services.i.data.worklist();
  }

  Future<void> _refresh() async {
    final next = Services.i.data.worklist();
    setState(() => _future = next);
    await next;
  }

  Future<void> _logout() async {
    await Services.i.auth.logout();
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const LoginScreen()),
      (_) => false,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('My Work'),
        actions: [
          IconButton(icon: const Icon(Icons.logout), tooltip: 'Sign out', onPressed: _logout),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: FutureBuilder<List<WorklistBucket>>(
          future: _future,
          builder: (context, snap) {
            if (snap.connectionState == ConnectionState.waiting) {
              return const Center(child: CircularProgressIndicator());
            }
            if (snap.hasError) {
              return _errorView('$snap'.contains('401')
                  ? 'Your session expired. Please sign in again.'
                  : 'Could not load your work.\n${snap.error}');
            }
            final buckets = snap.data ?? const [];
            if (buckets.isEmpty) {
              return _scrollable(const Center(child: Text('Nothing needs your attention. 🎉')));
            }
            return ListView(
              padding: const EdgeInsets.all(16),
              children: [for (final b in buckets) _BucketSection(b)],
            );
          },
        ),
      ),
    );
  }

  Widget _scrollable(Widget child) =>
      ListView(children: [const SizedBox(height: 160), child]);

  Widget _errorView(String msg) => _scrollable(Padding(
        padding: const EdgeInsets.all(24),
        child: Column(children: [
          const Icon(Icons.error_outline, size: 48, color: Colors.black26),
          const SizedBox(height: 12),
          Text(msg, textAlign: TextAlign.center, style: const TextStyle(color: Colors.black54)),
          const SizedBox(height: 12),
          FilledButton.tonal(onPressed: _refresh, child: const Text('Retry')),
        ]),
      ));
}

class _BucketSection extends StatelessWidget {
  const _BucketSection(this.bucket);
  final WorklistBucket bucket;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(4, 8, 4, 8),
          child: Row(
            children: [
              Text(bucket.label,
                  style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
              const SizedBox(width: 8),
              _CountBadge(bucket.count),
            ],
          ),
        ),
        if (bucket.items.isEmpty)
          const Padding(
            padding: EdgeInsets.fromLTRB(4, 0, 4, 12),
            child: Text('All clear.', style: TextStyle(color: Colors.black45)),
          )
        else
          Card(
            margin: const EdgeInsets.only(bottom: 20),
            child: Column(
              children: [
                for (final item in bucket.items)
                  ListTile(
                    dense: true,
                    title: Text(_title(item)),
                    subtitle: Text(_subtitle(bucket.key, item)),
                    trailing: const Icon(Icons.chevron_right, size: 18),
                    onTap: () {}, // drill-in screens are the next to build
                  ),
              ],
            ),
          ),
      ],
    );
  }

  String _title(Map<String, dynamic> j) => (j['lead_name'] ??
          j['full_name'] ??
          j['title'] ??
          j['milestone'] ??
          j['note'] ??
          j['id'] ??
          '—')
      .toString();

  String _subtitle(String key, Map<String, dynamic> j) {
    switch (key) {
      case 'estimate_approvals':
        return 'v${j['version'] ?? '?'} · ₹${j['total'] ?? '—'}';
      case 'expense_approvals':
        return '₹${j['amount'] ?? '—'}';
      case 'my_open_tickets':
        return '${j['kind'] ?? 'issue'} · ${j['priority'] ?? 'normal'}';
      case 'my_followups':
        return 'Stage ${j['stage'] ?? '—'} · ${j['phone'] ?? ''}';
      default:
        return '';
    }
  }
}

class _CountBadge extends StatelessWidget {
  const _CountBadge(this.count);
  final int count;

  @override
  Widget build(BuildContext context) {
    final color = count > 0 ? Theme.of(context).colorScheme.primary : Colors.black26;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 2),
      decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(12)),
      child: Text('$count',
          style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700, fontSize: 12)),
    );
  }
}
