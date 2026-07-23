import 'package:flutter/material.dart';
import 'package:ij_core/ij_core.dart';

import '../services.dart';
import '../widgets.dart';
import 'checklists_screen.dart';
import 'cutlist_screen.dart';

/// The journey stages a part moves through (mirrors backend PART_STAGES).
const List<String> kPartStages = [
  'ingested', 'in_production', 'qc', 'rework', 'assembly',
  'packed', 'loaded', 'dispatched', 'unloaded', 'installed', 'ticketed',
];
const List<String> kTicketKinds = ['damaged', 'missing', 'fitting'];

/// Projects tab: the projects this employee can see (contract §5.3).
class ProjectsTab extends StatelessWidget {
  const ProjectsTab({super.key});

  @override
  Widget build(BuildContext context) {
    return AsyncRefresh<List<Map<String, dynamic>>>(
      load: Services.i.data.projects,
      onData: (projects, refresh) {
        if (projects.isEmpty) {
          return const EmptyState(
            icon: Icons.factory_outlined,
            text: 'No projects yet.\nProjects appear once a booking is paid.',
          );
        }
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            for (final p in projects)
              Card(
                margin: const EdgeInsets.only(bottom: 12),
                child: ListTile(
                  title: Text(p['customer_name']?.toString() ?? 'Project',
                      style: const TextStyle(fontWeight: FontWeight.w600)),
                  subtitle: Text([
                    p['project_code']?.toString(),
                    p['city']?.toString(),
                    inr(p['contract_value'] as num?),
                  ].whereType<String>().where((s) => s.isNotEmpty).join(' · ')),
                  trailing: (p['sent_to_factory'] == true)
                      ? const StatusChip('In factory', color: Color(0xFF4A5D23))
                      : (p['booking_paid'] == true ? const StatusChip('Active') : null),
                  onTap: () => Navigator.of(context).push(
                    MaterialPageRoute(builder: (_) => ProjectDetailScreen(project: p)),
                  ),
                ),
              ),
          ],
        );
      },
    );
  }
}

class ProjectDetailScreen extends StatefulWidget {
  const ProjectDetailScreen({super.key, required this.project});
  final Map<String, dynamic> project;

  @override
  State<ProjectDetailScreen> createState() => _ProjectDetailScreenState();
}

class _ProjectDetailScreenState extends State<ProjectDetailScreen> {
  String get _id => widget.project['id'] as String;

  Future<(Map<String, dynamic>, List<Map<String, dynamic>>)> _load() async {
    final detail = await Services.i.data.project(_id);
    final parts = await Services.i.data.parts(_id);
    return (detail, parts);
  }

  Future<void> _openScan({String? partUid, required Future<void> Function() refresh}) async {
    final ok = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      builder: (_) => _ScanSheet(prefillPartUid: partUid),
    );
    if (ok == true && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Scan recorded ✓')));
      refresh();
    }
  }

  Future<void> _openTicket({String? partUid, required Future<void> Function() refresh}) async {
    final ok = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      builder: (_) => TicketSheet(projectId: _id, prefillPartUid: partUid),
    );
    if (ok == true && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Ticket raised ✓')));
      refresh();
    }
  }

  Future<void> _openExpense() async {
    final ok = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      builder: (_) => _ExpenseSheet(projectId: _id),
    );
    if (ok == true && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Expense submitted for approval ✓')));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(widget.project['project_code']?.toString() ?? 'Project')),
      body: AsyncRefresh<(Map<String, dynamic>, List<Map<String, dynamic>>)>(
        load: _load,
        onData: (data, refresh) {
          final detail = data.$1;
          final parts = data.$2;
          final production = (detail['production'] as Map?)?.cast<String, dynamic>() ?? const {};
          final byStatus = (production['by_status'] as Map?)?.cast<String, dynamic>() ?? const {};
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              _HeaderCard(detail),
              const SizedBox(height: 20),
              Row(children: [
                const Text('Production', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
                const SizedBox(width: 8),
                Text('${production['total_parts'] ?? 0} parts', style: const TextStyle(color: Colors.black54)),
              ]),
              const SizedBox(height: 10),
              if (byStatus.isEmpty)
                const Text('No parts ingested yet. Import the Infurnia cut list to begin.',
                    style: TextStyle(color: Colors.black54))
              else
                Wrap(spacing: 8, runSpacing: 8, children: [
                  for (final e in byStatus.entries) StatusChip('${e.key}: ${e.value}'),
                ]),
              const SizedBox(height: 20),
              Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
                const Text('Parts', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
                Row(children: [
                  TextButton.icon(
                    onPressed: () async {
                      await Navigator.of(context).push(MaterialPageRoute(
                        builder: (_) => CutlistIngestScreen(
                          projectId: _id,
                          projectCode: widget.project['project_code']?.toString(),
                        ),
                      ));
                      refresh();
                    },
                    icon: const Icon(Icons.upload_file, size: 18),
                    label: const Text('Import'),
                  ),
                  TextButton.icon(
                    onPressed: () => _openScan(refresh: refresh),
                    icon: const Icon(Icons.qr_code_scanner, size: 18),
                    label: const Text('Scan'),
                  ),
                ]),
              ]),
              if (parts.isEmpty)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 16),
                  child: Text('No parts yet.', style: TextStyle(color: Colors.black54)),
                )
              else
                Card(
                  child: Column(children: [
                    for (final part in parts)
                      ListTile(
                        dense: true,
                        title: Text(part['part_uid']?.toString() ?? '—',
                            style: const TextStyle(fontWeight: FontWeight.w600)),
                        subtitle: Text([part['name'], part['material'], part['dimensions']]
                            .whereType<String>()
                            .join(' · ')),
                        trailing: StatusChip(part['status']?.toString() ?? 'ingested'),
                        onTap: () => _openScan(partUid: part['part_uid']?.toString(), refresh: refresh),
                        onLongPress: () => _openTicket(partUid: part['part_uid']?.toString(), refresh: refresh),
                      ),
                  ]),
                ),
              const SizedBox(height: 24),
              FilledButton.tonalIcon(
                onPressed: () => Navigator.of(context).push(MaterialPageRoute(
                  builder: (_) => ChecklistsScreen(
                    projectId: _id,
                    projectCode: widget.project['project_code']?.toString(),
                  ),
                )),
                icon: const Icon(Icons.fact_check_outlined),
                label: const Text('Checklists & site reconciliation'),
                style: FilledButton.styleFrom(padding: const EdgeInsets.symmetric(vertical: 14)),
              ),
              const SizedBox(height: 10),
              OutlinedButton.icon(
                onPressed: () => _openTicket(refresh: refresh),
                icon: const Icon(Icons.report_problem_outlined),
                label: const Text('Raise a ticket'),
                style: OutlinedButton.styleFrom(padding: const EdgeInsets.symmetric(vertical: 14)),
              ),
              const SizedBox(height: 10),
              OutlinedButton.icon(
                onPressed: _openExpense,
                icon: const Icon(Icons.receipt_long_outlined),
                label: const Text('Submit an expense'),
                style: OutlinedButton.styleFrom(padding: const EdgeInsets.symmetric(vertical: 14)),
              ),
              const SizedBox(height: 8),
              const Center(
                child: Text('Tip: tap a part to scan it, long-press to raise a ticket',
                    style: TextStyle(color: Colors.black38, fontSize: 12)),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _HeaderCard extends StatelessWidget {
  const _HeaderCard(this.d);
  final Map<String, dynamic> d;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(d['customer_name']?.toString() ?? 'Project',
              style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
          const SizedBox(height: 4),
          Text([d['city'], d['phone']].whereType<String>().join(' · '),
              style: const TextStyle(color: Colors.black54)),
          const Divider(height: 20),
          _row('Contract', inr(d['contract_value'] as num?)),
          _row('Booking', d['booking_paid'] == true ? 'Paid ✓' : 'Pending'),
          _row('Factory', d['sent_to_factory'] == true ? 'Handed over' : 'Not yet'),
        ]),
      ),
    );
  }

  Widget _row(String k, String v) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 3),
        child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
          Text(k, style: const TextStyle(color: Colors.black54)),
          Text(v, style: const TextStyle(fontWeight: FontWeight.w600)),
        ]),
      );
}

/// Record a QR scan and advance a part's stage (contract §5.5).
class _ScanSheet extends StatefulWidget {
  const _ScanSheet({this.prefillPartUid});
  final String? prefillPartUid;

  @override
  State<_ScanSheet> createState() => _ScanSheetState();
}

class _ScanSheetState extends State<_ScanSheet> {
  late final TextEditingController _code =
      TextEditingController(text: widget.prefillPartUid ?? '');
  final _station = TextEditingController();
  String _toStage = 'qc';
  bool _busy = false;
  String? _error;

  Future<void> _submit() async {
    if (_code.text.trim().isEmpty || _station.text.trim().isEmpty) {
      setState(() => _error = 'Scan/enter a code and a station.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      // Camera scanning fills `_code` — see SCANNER_SETUP.md to activate
      // mobile_scanner; manual entry works today. Match is by part_uid or QR value.
      await Services.i.data.scanPart(
        partUid: _code.text.trim(),
        qrValue: _code.text.trim(),
        station: _station.text.trim(),
        toStage: _toStage,
      );
      if (mounted) Navigator.pop(context, true);
    } on ApiException catch (e) {
      setState(() {
        _error = e.message;
        _busy = false;
      });
    } catch (_) {
      setState(() {
        _error = 'Scan failed.';
        _busy = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        left: 20, right: 20, top: 20, bottom: MediaQuery.of(context).viewInsets.bottom + 20),
      child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        const Text('Scan a part', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
        const SizedBox(height: 16),
        TextField(
          controller: _code,
          decoration: const InputDecoration(
            labelText: 'Part ID / QR value',
            prefixIcon: Icon(Icons.qr_code_2),
            border: OutlineInputBorder(),
          ),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _station,
          decoration: const InputDecoration(
            labelText: 'Station (e.g. QC, Assembly)',
            border: OutlineInputBorder(),
          ),
        ),
        const SizedBox(height: 12),
        DropdownButtonFormField<String>(
          value: _toStage,
          decoration: const InputDecoration(labelText: 'Advance to stage', border: OutlineInputBorder()),
          items: [for (final s in kPartStages) DropdownMenuItem(value: s, child: Text(s))],
          onChanged: _busy ? null : (v) => setState(() => _toStage = v ?? _toStage),
        ),
        if (_error != null) ...[
          const SizedBox(height: 10),
          Text(_error!, style: const TextStyle(color: Colors.red)),
        ],
        const SizedBox(height: 16),
        FilledButton(
          onPressed: _busy ? null : _submit,
          style: FilledButton.styleFrom(padding: const EdgeInsets.symmetric(vertical: 14)),
          child: _busy
              ? const SizedBox(height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
              : const Text('Record scan'),
        ),
        TextButton(onPressed: _busy ? null : () => Navigator.pop(context, false), child: const Text('Cancel')),
      ]),
    );
  }
}

/// Raise a site/production ticket (contract §5.6).
class TicketSheet extends StatefulWidget {
  const TicketSheet({required this.projectId, this.prefillPartUid});
  final String projectId;
  final String? prefillPartUid;

  @override
  State<TicketSheet> createState() => TicketSheetState();
}

class TicketSheetState extends State<TicketSheet> {
  final _title = TextEditingController();
  String _kind = 'damaged';
  bool _busy = false;
  String? _error;

  Future<void> _submit() async {
    if (_title.text.trim().isEmpty) {
      setState(() => _error = 'Add a short title.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await Services.i.data.raiseTicket(
        projectId: widget.projectId,
        kind: _kind,
        title: _title.text.trim(),
        partUid: widget.prefillPartUid,
      );
      if (mounted) Navigator.pop(context, true);
    } on ApiException catch (e) {
      setState(() {
        _error = e.message;
        _busy = false;
      });
    } catch (_) {
      setState(() {
        _error = 'Could not raise the ticket.';
        _busy = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        left: 20, right: 20, top: 20, bottom: MediaQuery.of(context).viewInsets.bottom + 20),
      child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Text(widget.prefillPartUid == null ? 'Raise a ticket' : 'Ticket · ${widget.prefillPartUid}',
            style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
        const SizedBox(height: 16),
        DropdownButtonFormField<String>(
          value: _kind,
          decoration: const InputDecoration(labelText: 'Type', border: OutlineInputBorder()),
          items: [for (final k in kTicketKinds) DropdownMenuItem(value: k, child: Text(k))],
          onChanged: _busy ? null : (v) => setState(() => _kind = v ?? _kind),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _title,
          decoration: const InputDecoration(labelText: 'What is wrong?', border: OutlineInputBorder()),
        ),
        if (_error != null) ...[
          const SizedBox(height: 10),
          Text(_error!, style: const TextStyle(color: Colors.red)),
        ],
        const SizedBox(height: 16),
        FilledButton(
          onPressed: _busy ? null : _submit,
          style: FilledButton.styleFrom(padding: const EdgeInsets.symmetric(vertical: 14)),
          child: _busy
              ? const SizedBox(height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
              : const Text('Raise ticket'),
        ),
        TextButton(onPressed: _busy ? null : () => Navigator.pop(context, false), child: const Text('Cancel')),
      ]),
    );
  }
}

/// Submit a site expense for approval (contract §5.8; gated by expenses.submit).
class _ExpenseSheet extends StatefulWidget {
  const _ExpenseSheet({required this.projectId});
  final String projectId;

  @override
  State<_ExpenseSheet> createState() => _ExpenseSheetState();
}

class _ExpenseSheetState extends State<_ExpenseSheet> {
  final _amount = TextEditingController();
  final _note = TextEditingController();
  bool _busy = false;
  String? _error;

  Future<void> _submit() async {
    final amount = num.tryParse(_amount.text.trim());
    if (amount == null || amount <= 0) {
      setState(() => _error = 'Enter an amount greater than 0.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await Services.i.data.submitExpense(
        projectId: widget.projectId,
        amount: amount,
        note: _note.text.trim().isEmpty ? null : _note.text.trim(),
      );
      if (mounted) Navigator.pop(context, true);
    } on ApiException catch (e) {
      setState(() {
        _error = e.statusCode == 403 ? 'You do not have permission to submit expenses.' : e.message;
        _busy = false;
      });
    } catch (_) {
      setState(() {
        _error = 'Could not submit the expense.';
        _busy = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        left: 20, right: 20, top: 20, bottom: MediaQuery.of(context).viewInsets.bottom + 20),
      child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        const Text('Submit an expense', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
        const SizedBox(height: 16),
        TextField(
          controller: _amount,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: const InputDecoration(
            labelText: 'Amount (₹)',
            prefixText: '₹ ',
            border: OutlineInputBorder(),
          ),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _note,
          decoration: const InputDecoration(labelText: 'What was it for?', border: OutlineInputBorder()),
        ),
        if (_error != null) ...[
          const SizedBox(height: 10),
          Text(_error!, style: const TextStyle(color: Colors.red)),
        ],
        const SizedBox(height: 16),
        FilledButton(
          onPressed: _busy ? null : _submit,
          style: FilledButton.styleFrom(padding: const EdgeInsets.symmetric(vertical: 14)),
          child: _busy
              ? const SizedBox(height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
              : const Text('Submit for approval'),
        ),
        TextButton(onPressed: _busy ? null : () => Navigator.pop(context, false), child: const Text('Cancel')),
      ]),
    );
  }
}
