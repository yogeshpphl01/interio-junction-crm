import 'package:flutter/material.dart';
import 'package:ij_core/ij_core.dart';

import '../services.dart';
import '../widgets.dart';

/// DPDP erasure queue for staff (needs `users.manage`). Lists data-subject
/// erasure requests and lets an admin fulfil (anonymize customer + leads,
/// retaining tax/legal records per DPDP §8(7)) or reject them. Fulfilment can
/// require a fresh step-up: on a 403 we prompt for the authenticator code,
/// exchange it for an elevation token, and retry with `X-Step-Up-Token`.
class PrivacyQueueScreen extends StatefulWidget {
  const PrivacyQueueScreen({super.key});

  @override
  State<PrivacyQueueScreen> createState() => _PrivacyQueueScreenState();
}

class _PrivacyQueueScreenState extends State<PrivacyQueueScreen> {
  final _data = Services.i.data;
  String _status = 'pending';

  static const _tabs = ['pending', 'completed', 'rejected', 'all'];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Data erasure requests'),
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(48),
          child: SizedBox(
            height: 48,
            child: ListView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: 12),
              children: [
                for (final t in _tabs)
                  Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: ChoiceChip(
                      label: Text(t[0].toUpperCase() + t.substring(1)),
                      selected: _status == t,
                      onSelected: (_) => setState(() => _status = t),
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
      // Rebuild the loader when the status filter changes.
      body: AsyncRefresh<List<Map<String, dynamic>>>(
        key: ValueKey(_status),
        load: () => _data.erasureRequests(status: _status),
        onData: (rows, refresh) {
          if (rows.isEmpty) {
            return const EmptyState(
                icon: Icons.privacy_tip_outlined, text: 'No requests here.');
          }
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              const _Note(
                'Fulfilling a request removes the customer’s personal details from '
                'their record and enquiries. Invoices and other records the business '
                'must keep by law are retained.',
              ),
              const SizedBox(height: 12),
              for (final r in rows)
                _RequestCard(
                  row: r,
                  onErase: () => _erase(r, refresh),
                  onReject: () => _reject(r, refresh),
                ),
            ],
          );
        },
      ),
    );
  }

  Future<void> _erase(Map<String, dynamic> r, Future<void> Function() refresh) async {
    final name = (r['customer_name'] ?? 'this customer').toString();
    final ok = await _confirm(
      title: 'Erase $name?',
      body: "This can't be undone. Personal details are removed now; "
          'transactional records are kept for legal retention.',
      danger: 'Erase',
    );
    if (ok != true) return;
    final customerId = r['customer_id'].toString();
    try {
      await _data.eraseCustomer(customerId);
      _snack('Customer erased.');
      await refresh();
    } on ApiException catch (e) {
      // Step-up required → collect a code, elevate, and retry once.
      if (e.statusCode == 403) {
        final token = await _elevate();
        if (token == null) return;
        try {
          await _data.eraseCustomer(customerId, stepUpToken: token);
          _snack('Customer erased.');
          await refresh();
        } catch (_) {
          _snack('Could not erase. Check your code and try again.');
        }
      } else {
        _snack(e.message);
      }
    } catch (_) {
      _snack('Could not erase.');
    }
  }

  Future<void> _reject(Map<String, dynamic> r, Future<void> Function() refresh) async {
    final ok = await _confirm(
      title: 'Reject this request?',
      body: 'The request is closed and the reason is logged. Use this when the '
          'customer has an active project or outstanding dues.',
      danger: 'Reject',
    );
    if (ok != true) return;
    try {
      await _data.rejectErasure(r['id'].toString());
      _snack('Request rejected.');
      await refresh();
    } on ApiException catch (e) {
      _snack(e.message);
    } catch (_) {
      _snack('Could not reject.');
    }
  }

  /// Prompt for the authenticator code and exchange it for an elevation token.
  Future<String?> _elevate() async {
    final ctl = TextEditingController();
    final code = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Confirm it’s you'),
        content: TextField(
          controller: ctl,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(
            labelText: 'Authenticator code',
            hintText: '6-digit code',
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, ctl.text.trim()),
              child: const Text('Confirm')),
        ],
      ),
    );
    if (code == null || code.isEmpty) return null;
    try {
      return await Services.i.auth.stepUp(code);
    } catch (_) {
      _snack('That code didn’t work.');
      return null;
    }
  }

  Future<bool?> _confirm({
    required String title,
    required String body,
    required String danger,
  }) =>
      showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: Text(title),
          content: Text(body),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
            FilledButton(
              style: FilledButton.styleFrom(backgroundColor: Colors.red),
              onPressed: () => Navigator.pop(ctx, true),
              child: Text(danger),
            ),
          ],
        ),
      );

  void _snack(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
  }
}

class _RequestCard extends StatelessWidget {
  const _RequestCard({required this.row, required this.onErase, required this.onReject});
  final Map<String, dynamic> row;
  final VoidCallback onErase;
  final VoidCallback onReject;

  @override
  Widget build(BuildContext context) {
    final status = (row['status'] ?? 'pending').toString();
    final erased = row['already_erased'] == true;
    final pending = status == 'pending' && !erased;
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    (row['customer_name'] ?? '[erased]').toString(),
                    style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15),
                  ),
                ),
                StatusChip(erased ? 'erased' : status, color: _statusColor(status, erased)),
              ],
            ),
            if ((row['reason'] ?? '').toString().isNotEmpty) ...[
              const SizedBox(height: 6),
              Text(row['reason'].toString(), style: const TextStyle(color: Colors.black54)),
            ],
            const SizedBox(height: 4),
            Text('Requested ${_date(row['requested_at'])}',
                style: const TextStyle(color: Colors.black38, fontSize: 12)),
            if (pending) ...[
              const SizedBox(height: 12),
              Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  OutlinedButton(onPressed: onReject, child: const Text('Reject')),
                  const SizedBox(width: 8),
                  FilledButton(
                    style: FilledButton.styleFrom(backgroundColor: Colors.red),
                    onPressed: onErase,
                    child: const Text('Erase'),
                  ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }

  Color _statusColor(String status, bool erased) {
    if (erased || status == 'completed') return Colors.green;
    if (status == 'rejected') return Colors.grey;
    return Colors.orange;
  }

  String _date(dynamic iso) {
    if (iso == null) return '—';
    final s = iso.toString();
    return s.length >= 10 ? s.substring(0, 10) : s;
  }
}

class _Note extends StatelessWidget {
  const _Note(this.text);
  final String text;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.primary.withOpacity(0.06),
          borderRadius: BorderRadius.circular(10),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Icon(Icons.info_outline, size: 18, color: Colors.black45),
            const SizedBox(width: 8),
            Expanded(
              child: Text(text, style: const TextStyle(fontSize: 12, color: Colors.black54)),
            ),
          ],
        ),
      );
}
