import 'package:flutter/material.dart';

import '../services.dart';
import '../widgets.dart';

/// Estimates tab: the customer's shared/accepted estimates (contract §4.4).
class EstimatesTab extends StatelessWidget {
  const EstimatesTab({super.key});

  @override
  Widget build(BuildContext context) {
    return AsyncRefresh<List<Map<String, dynamic>>>(
      load: Services.i.data.estimates,
      onData: (estimates, refresh) {
        if (estimates.isEmpty) {
          return const EmptyState(
            icon: Icons.receipt_long_outlined,
            text: 'No estimates yet.\nYour designer will share one here.',
          );
        }
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            for (final e in estimates)
              Card(
                margin: const EdgeInsets.only(bottom: 12),
                child: ListTile(
                  title: Text('Estimate v${e['version'] ?? '?'}',
                      style: const TextStyle(fontWeight: FontWeight.w600)),
                  subtitle: Text(inr(e['total'] as num?)),
                  trailing: _statusChip(e['status'] as String?),
                  onTap: () async {
                    final changed = await Navigator.of(context).push<bool>(
                      MaterialPageRoute(builder: (_) => EstimateDetailScreen(estimate: e)),
                    );
                    if (changed == true) refresh();
                  },
                ),
              ),
          ],
        );
      },
    );
  }
}

Widget _statusChip(String? status) {
  switch (status) {
    case 'accepted':
      return const StatusChip('Accepted', color: Color(0xFF4A5D23));
    case 'shared':
      return const StatusChip('Review', color: Color(0xFFC99A4B));
    default:
      return StatusChip(status ?? '—', color: Colors.grey);
  }
}

/// Estimate detail with line items and, if it is still 'shared', an Accept action.
class EstimateDetailScreen extends StatefulWidget {
  const EstimateDetailScreen({super.key, required this.estimate});
  final Map<String, dynamic> estimate;

  @override
  State<EstimateDetailScreen> createState() => _EstimateDetailScreenState();
}

class _EstimateDetailScreenState extends State<EstimateDetailScreen> {
  bool _busy = false;
  late String _status = widget.estimate['status'] as String? ?? '';

  Future<void> _accept() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Accept this estimate?'),
        content: Text(
            'Accepting confirms ${inr(widget.estimate['total'] as num?)} and unlocks the 10% booking payment.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Accept')),
        ],
      ),
    );
    if (ok != true) return;
    setState(() => _busy = true);
    try {
      await Services.i.data.acceptEstimate(widget.estimate['id'] as String);
      if (!mounted) return;
      setState(() => _status = 'accepted');
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Estimate accepted. Thank you!')),
      );
      Navigator.pop(context, true); // tell the list to refresh
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
        setState(() => _busy = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final e = widget.estimate;
    final items = ((e['items'] as List?) ?? const []).cast<Map<String, dynamic>>();
    return Scaffold(
      appBar: AppBar(title: Text('Estimate v${e['version'] ?? '?'}')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Row(children: [_statusChip(_status)]),
          const SizedBox(height: 16),
          Card(
            child: Column(children: [
              for (final it in items)
                ListTile(
                  dense: true,
                  title: Text(it['description']?.toString() ?? 'Item'),
                  subtitle: Text('${it['quantity'] ?? 1} × ${inr(it['rate'] as num?)}'),
                  trailing: Text(inr(it['amount'] as num?),
                      style: const TextStyle(fontWeight: FontWeight.w600)),
                ),
            ]),
          ),
          const SizedBox(height: 16),
          _totalRow('Subtotal', e['subtotal'] as num?),
          _totalRow('Discount', e['discount'] as num?),
          _totalRow('Tax', e['tax'] as num?),
          const Divider(),
          _totalRow('Total', e['total'] as num?, bold: true),
          const SizedBox(height: 24),
          if (_status == 'shared')
            FilledButton(
              onPressed: _busy ? null : _accept,
              style: FilledButton.styleFrom(padding: const EdgeInsets.symmetric(vertical: 16)),
              child: _busy
                  ? const SizedBox(height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                  : const Text('Accept estimate'),
            )
          else if (_status == 'accepted')
            const Center(child: Text('You have accepted this estimate ✓', style: TextStyle(color: Color(0xFF4A5D23)))),
        ],
      ),
    );
  }

  Widget _totalRow(String k, num? v, {bool bold = false}) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 4, horizontal: 4),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(k, style: TextStyle(fontWeight: bold ? FontWeight.w700 : FontWeight.w400)),
            Text(inr(v),
                style: TextStyle(fontWeight: bold ? FontWeight.w700 : FontWeight.w500, fontSize: bold ? 18 : 14)),
          ],
        ),
      );
}
