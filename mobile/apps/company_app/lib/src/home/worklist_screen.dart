import 'package:flutter/material.dart';
import 'package:ij_core/ij_core.dart';

import '../services.dart';
import '../push/push_service.dart';
import '../auth/login_screen.dart';

/// Employee home: role-aware "things to act on" buckets (contract §5.2). Tapping
/// an item opens the right action sheet (approve/reject an estimate or expense,
/// resolve a ticket); the list refreshes after any action.
class WorklistScreen extends StatefulWidget {
  const WorklistScreen({super.key});

  @override
  State<WorklistScreen> createState() => _WorklistScreenState();
}

class _WorklistScreenState extends State<WorklistScreen> {
  late Future<List<WorklistBucket>> _future = Services.i.data.worklist();

  @override
  void initState() {
    super.initState();
    // Signed in — register this device for push (no-op until Firebase is configured).
    PushService.instance.registerAfterLogin(Services.i.auth.registerDevice);
  }

  Future<void> _refresh() async {
    final next = Services.i.data.worklist();
    setState(() => _future = next);
    await next;
  }

  Future<void> _logout() async {
    await PushService.instance.onLogout(Services.i.auth.unregisterDevice); // before tokens are cleared
    await Services.i.auth.logout();
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const LoginScreen()),
      (_) => false,
    );
  }

  Future<void> _openActions(String bucketKey, Map<String, dynamic> item) async {
    if (bucketKey == 'my_followups') return; // informational only
    final acted = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      builder: (_) => _ActionSheet(bucketKey: bucketKey, item: item),
    );
    if (acted == true && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Done ✓')));
      _refresh();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('My Work'),
        actions: [IconButton(icon: const Icon(Icons.logout), tooltip: 'Sign out', onPressed: _logout)],
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
              return ListView(children: [
                const SizedBox(height: 140),
                const Icon(Icons.error_outline, size: 48, color: Colors.black26),
                const SizedBox(height: 12),
                Center(child: Text('${snap.error}', style: const TextStyle(color: Colors.black54))),
                const SizedBox(height: 12),
                Center(child: FilledButton.tonal(onPressed: _refresh, child: const Text('Retry'))),
              ]);
            }
            final buckets = snap.data ?? const [];
            if (buckets.isEmpty) {
              return ListView(children: const [
                SizedBox(height: 160),
                Center(child: Text('Nothing needs your attention. 🎉')),
              ]);
            }
            return ListView(
              padding: const EdgeInsets.all(16),
              children: [for (final b in buckets) _BucketSection(bucket: b, onTap: _openActions)],
            );
          },
        ),
      ),
    );
  }
}

class _BucketSection extends StatelessWidget {
  const _BucketSection({required this.bucket, required this.onTap});
  final WorklistBucket bucket;
  final void Function(String bucketKey, Map<String, dynamic> item) onTap;

  bool get _actionable => bucket.key != 'my_followups';

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(4, 8, 4, 8),
          child: Row(children: [
            Text(bucket.label, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
            const SizedBox(width: 8),
            _CountBadge(bucket.count),
          ]),
        ),
        if (bucket.items.isEmpty)
          const Padding(
            padding: EdgeInsets.fromLTRB(4, 0, 4, 12),
            child: Text('All clear.', style: TextStyle(color: Colors.black45)),
          )
        else
          Card(
            margin: const EdgeInsets.only(bottom: 20),
            child: Column(children: [
              for (final item in bucket.items)
                ListTile(
                  dense: true,
                  title: Text(_title(item)),
                  subtitle: Text(_subtitle(bucket.key, item)),
                  trailing: _actionable ? const Icon(Icons.chevron_right, size: 18) : null,
                  onTap: _actionable ? () => onTap(bucket.key, item) : null,
                ),
            ]),
          ),
      ],
    );
  }

  String _title(Map<String, dynamic> j) =>
      (j['lead_name'] ?? j['full_name'] ?? j['title'] ?? j['milestone'] ?? j['note'] ?? j['id'] ?? '—')
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

/// The per-item action sheet. Approve/reject an estimate or expense, or resolve a
/// ticket (with an optional "send back to production" flag). Pops `true` on success.
class _ActionSheet extends StatefulWidget {
  const _ActionSheet({required this.bucketKey, required this.item});
  final String bucketKey;
  final Map<String, dynamic> item;

  @override
  State<_ActionSheet> createState() => _ActionSheetState();
}

class _ActionSheetState extends State<_ActionSheet> {
  bool _busy = false;
  bool _remanufacture = false;
  String? _error;

  String get _id => widget.item['id'].toString();

  Future<void> _do(Future<void> Function() action) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await action();
      if (mounted) Navigator.pop(context, true);
    } on ApiException catch (e) {
      setState(() {
        _error = e.message;
        _busy = false;
      });
    } catch (_) {
      setState(() {
        _error = 'Something went wrong.';
        _busy = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final data = Services.i.data;
    return Padding(
      padding: EdgeInsets.only(
        left: 20, right: 20, top: 20,
        bottom: MediaQuery.of(context).viewInsets.bottom + 20,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(_heading(), style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
          const SizedBox(height: 16),
          if (widget.bucketKey == 'my_open_tickets')
            CheckboxListTile(
              contentPadding: EdgeInsets.zero,
              value: _remanufacture,
              onChanged: _busy ? null : (v) => setState(() => _remanufacture = v ?? false),
              title: const Text('Send the linked part back to production'),
            ),
          if (_error != null) ...[
            Text(_error!, style: const TextStyle(color: Colors.red)),
            const SizedBox(height: 8),
          ],
          if (_busy)
            const Padding(padding: EdgeInsets.all(8), child: Center(child: CircularProgressIndicator()))
          else ...[
            for (final a in _actions(data))
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: a,
              ),
          ],
          TextButton(
            onPressed: _busy ? null : () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
        ],
      ),
    );
  }

  String _heading() {
    switch (widget.bucketKey) {
      case 'estimate_approvals':
        return 'Estimate v${widget.item['version'] ?? '?'} · ₹${widget.item['total'] ?? '—'}';
      case 'expense_approvals':
        return 'Expense · ₹${widget.item['amount'] ?? '—'}';
      case 'my_open_tickets':
        return widget.item['title']?.toString() ?? 'Ticket';
      default:
        return 'Action';
    }
  }

  List<Widget> _actions(CompanyRepository data) {
    switch (widget.bucketKey) {
      case 'estimate_approvals':
        return [
          FilledButton(onPressed: () => _do(() => data.approveEstimate(_id)), child: const Text('Approve')),
          OutlinedButton(onPressed: () => _do(() => data.rejectEstimate(_id)), child: const Text('Send back for changes')),
        ];
      case 'expense_approvals':
        return [
          FilledButton(onPressed: () => _do(() => data.approveExpense(_id)), child: const Text('Approve')),
          OutlinedButton(onPressed: () => _do(() => data.rejectExpense(_id)), child: const Text('Reject')),
        ];
      case 'my_open_tickets':
        return [
          FilledButton(
              onPressed: () => _do(() => data.resolveTicket(_id, remanufacture: _remanufacture)),
              child: const Text('Mark resolved')),
        ];
      default:
        return const [];
    }
  }
}
