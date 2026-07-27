import 'package:flutter/material.dart';

import '../services.dart';
import '../widgets.dart';

/// Payments tab: paid/balance summary + history (contract §4.6).
class PaymentsTab extends StatelessWidget {
  const PaymentsTab({super.key});

  @override
  Widget build(BuildContext context) {
    return AsyncRefresh<Map<String, dynamic>>(
      load: Services.i.data.payments,
      onData: (data, refresh) {
        final summary = (data['summary'] as Map?)?.cast<String, dynamic>() ?? const {};
        final payments = ((data['payments'] as List?) ?? const []).cast<Map<String, dynamic>>();
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            _SummaryCard(summary),
            const SizedBox(height: 20),
            const Padding(
              padding: EdgeInsets.only(left: 4, bottom: 8),
              child: Text('History', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
            ),
            if (payments.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 24),
                child: Center(child: Text('No payments yet.', style: TextStyle(color: Colors.black54))),
              )
            else
              Card(
                child: Column(children: [
                  for (final p in payments)
                    ListTile(
                      leading: Icon(_paid(p) ? Icons.check_circle : Icons.schedule,
                          color: _paid(p) ? const Color(0xFF4A5D23) : Colors.orange),
                      title: Text(p['milestone']?.toString() ?? (p['type']?.toString() ?? 'Payment')),
                      subtitle: Text([
                        p['method']?.toString(),
                        p['paid_date']?.toString()?.split('T').first,
                      ].whereType<String>().join(' · ')),
                      trailing: Text(inr(p['amount'] as num?),
                          style: const TextStyle(fontWeight: FontWeight.w600)),
                    ),
                ]),
              ),
          ],
        );
      },
    );
  }

  bool _paid(Map<String, dynamic> p) {
    final s = (p['status'] as String?)?.toLowerCase();
    return s == 'verified' || s == 'paid';
  }
}

class _SummaryCard extends StatelessWidget {
  const _SummaryCard(this.s);
  final Map<String, dynamic> s;

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      color: Theme.of(context).colorScheme.primary.withOpacity(0.08),
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(children: [
          Text(inr(s['balance'] as num?),
              style: const TextStyle(fontSize: 30, fontWeight: FontWeight.w800)),
          const Text('Balance due', style: TextStyle(color: Colors.black54)),
          const Divider(height: 28),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: [
              _stat('Contract', inr(s['contract_value'] as num?)),
              _stat('Paid', inr(s['paid'] as num?)),
            ],
          ),
        ]),
      ),
    );
  }

  Widget _stat(String k, String v) => Column(children: [
        Text(v, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
        Text(k, style: const TextStyle(color: Colors.black54, fontSize: 12)),
      ]);
}
