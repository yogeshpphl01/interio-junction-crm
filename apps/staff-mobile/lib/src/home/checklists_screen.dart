import 'package:flutter/material.dart';
import 'package:ij_core/ij_core.dart';

import '../services.dart';
import '../widgets.dart';
import 'projects_screen.dart' show TicketSheet;

const List<String> kChecklistTypes = ['factory', 'pack', 'load', 'unload', 'install', 'closure'];

/// Site-ops for a project: the load/unload reconciliation and the digital
/// checklists (contract §5.7).
class ChecklistsScreen extends StatefulWidget {
  const ChecklistsScreen({super.key, required this.projectId, this.projectCode});
  final String projectId;
  final String? projectCode;

  @override
  State<ChecklistsScreen> createState() => _ChecklistsScreenState();
}

class _ChecklistsScreenState extends State<ChecklistsScreen> {
  Future<(Map<String, dynamic>, List<Map<String, dynamic>>)> _load() async {
    final recon = await Services.i.data.reconciliation(widget.projectId);
    final lists = await Services.i.data.checklists(widget.projectId);
    return (recon, lists);
  }

  Future<void> _newChecklist(Future<void> Function() refresh) async {
    final created = await showModalBottomSheet<Map<String, dynamic>>(
      context: context,
      isScrollControlled: true,
      builder: (_) => _NewChecklistSheet(projectId: widget.projectId),
    );
    if (created != null && mounted) {
      await Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => ChecklistDetailScreen(checklistId: created['id'] as String),
      ));
      refresh();
    }
  }

  Future<void> _raiseForMissing(String partUid, Future<void> Function() refresh) async {
    final ok = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      builder: (_) => TicketSheet(projectId: widget.projectId, prefillPartUid: partUid),
    );
    if (ok == true && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Ticket raised ✓')));
      refresh();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(widget.projectCode == null ? 'Site ops' : 'Site ops · ${widget.projectCode}')),
      body: AsyncRefresh<(Map<String, dynamic>, List<Map<String, dynamic>>)>(
        load: _load,
        onData: (data, refresh) {
          final recon = data.$1;
          final lists = data.$2;
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              _ReconCard(recon: recon, onRaise: (uid) => _raiseForMissing(uid, refresh)),
              const SizedBox(height: 20),
              Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
                const Text('Checklists', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
                TextButton.icon(
                  onPressed: () => _newChecklist(refresh),
                  icon: const Icon(Icons.add, size: 18),
                  label: const Text('New'),
                ),
              ]),
              if (lists.isEmpty)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 16),
                  child: Text('No checklists yet.', style: TextStyle(color: Colors.black54)),
                )
              else
                Card(
                  child: Column(children: [
                    for (final c in lists)
                      ListTile(
                        dense: true,
                        leading: Icon(c['status'] == 'completed'
                            ? Icons.check_circle
                            : Icons.radio_button_unchecked,
                            color: c['status'] == 'completed' ? const Color(0xFF4A5D23) : Colors.orange),
                        title: Text((c['type']?.toString() ?? 'checklist').toUpperCase(),
                            style: const TextStyle(fontWeight: FontWeight.w600)),
                        subtitle: Text(c['status']?.toString() ?? 'open'),
                        trailing: const Icon(Icons.chevron_right, size: 18),
                        onTap: () async {
                          await Navigator.of(context).push(MaterialPageRoute(
                            builder: (_) => ChecklistDetailScreen(checklistId: c['id'] as String),
                          ));
                          refresh();
                        },
                      ),
                  ]),
                ),
            ],
          );
        },
      ),
    );
  }
}

class _ReconCard extends StatelessWidget {
  const _ReconCard({required this.recon, required this.onRaise});
  final Map<String, dynamic> recon;
  final void Function(String partUid) onRaise;

  @override
  Widget build(BuildContext context) {
    final reconciled = recon['reconciled'] == true;
    final missing = ((recon['missing_parts'] as List?) ?? const []).cast<Map<String, dynamic>>();
    final loaded = recon['loaded_count'] ?? 0;
    final unloaded = recon['unloaded_count'] ?? 0;
    final missingCount = recon['missing_count'] ?? 0;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            const Text('Load / unload reconciliation',
                style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
            const Spacer(),
            reconciled
                ? const StatusChip('Reconciled', color: Color(0xFF4A5D23))
                : (loaded == 0
                    ? const StatusChip('No dispatch yet', color: Colors.grey)
                    : StatusChip('$missingCount missing', color: const Color(0xFFA95A3F))),
          ]),
          const SizedBox(height: 12),
          Row(mainAxisAlignment: MainAxisAlignment.spaceAround, children: [
            _stat('Loaded', '$loaded'),
            _stat('Unloaded', '$unloaded'),
            _stat('Missing', '$missingCount'),
          ]),
          if (missing.isNotEmpty) ...[
            const Divider(height: 24),
            const Text('Loaded but not unloaded on site:',
                style: TextStyle(fontWeight: FontWeight.w600)),
            const SizedBox(height: 4),
            for (final p in missing)
              ListTile(
                dense: true,
                contentPadding: EdgeInsets.zero,
                title: Text(p['part_uid']?.toString() ?? '—'),
                subtitle: Text(p['name']?.toString() ?? ''),
                trailing: TextButton(
                  onPressed: () => onRaise(p['part_uid'].toString()),
                  child: const Text('Raise ticket'),
                ),
              ),
          ],
        ]),
      ),
    );
  }

  Widget _stat(String k, String v) => Column(children: [
        Text(v, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800)),
        Text(k, style: const TextStyle(color: Colors.black54, fontSize: 12)),
      ]);
}

/// A single checklist: check items off, add items, then complete (e-sign).
class ChecklistDetailScreen extends StatefulWidget {
  const ChecklistDetailScreen({super.key, required this.checklistId});
  final String checklistId;

  @override
  State<ChecklistDetailScreen> createState() => _ChecklistDetailScreenState();
}

class _ChecklistDetailScreenState extends State<ChecklistDetailScreen> {
  Map<String, dynamic>? _checklist;
  List<Map<String, dynamic>> _items = [];
  final _newItem = TextEditingController();
  bool _loading = true;
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  Future<void> _reload() async {
    setState(() => _loading = true);
    try {
      final c = await Services.i.data.checklist(widget.checklistId);
      setState(() {
        _checklist = c;
        _items = ((c['items'] as List?) ?? const []).cast<Map<String, dynamic>>();
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _error = '$e';
        _loading = false;
      });
    }
  }

  bool get _completed => _checklist?['status'] == 'completed';

  Future<void> _toggle(Map<String, dynamic> item, bool value) async {
    setState(() => item['checked'] = value); // optimistic
    try {
      await Services.i.data.setChecklistItemChecked(widget.checklistId, item['id'] as String, value);
    } catch (_) {
      setState(() => item['checked'] = !value); // revert
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Could not update item')));
      }
    }
  }

  Future<void> _addItem() async {
    final label = _newItem.text.trim();
    if (label.isEmpty) return;
    setState(() => _busy = true);
    try {
      final item = await Services.i.data.addChecklistItem(widget.checklistId, label);
      setState(() {
        _items.add(item);
        _newItem.clear();
      });
    } catch (_) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Could not add item')));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _complete() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await Services.i.data.completeChecklist(widget.checklistId);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Checklist completed ✓')));
      Navigator.pop(context, true);
    } on ApiException catch (e) {
      setState(() {
        _error = e.message; // e.g. "3 item(s) still unchecked"
        _busy = false;
      });
    } catch (_) {
      setState(() {
        _error = 'Could not complete the checklist.';
        _busy = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final type = (_checklist?['type']?.toString() ?? 'checklist').toUpperCase();
    return Scaffold(
      appBar: AppBar(
        title: Text(type),
        actions: [
          if (_completed)
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 12),
              child: Center(child: StatusChip('Completed', color: Color(0xFF4A5D23))),
            ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                if (_items.isEmpty)
                  const Padding(
                    padding: EdgeInsets.symmetric(vertical: 12),
                    child: Text('No items yet — add the first one below.',
                        style: TextStyle(color: Colors.black54)),
                  )
                else
                  Card(
                    child: Column(children: [
                      for (final item in _items)
                        CheckboxListTile(
                          value: item['checked'] == true,
                          onChanged: _completed ? null : (v) => _toggle(item, v ?? false),
                          title: Text(item['label']?.toString() ?? ''),
                          subtitle: item['note'] != null ? Text(item['note'].toString()) : null,
                          controlAffinity: ListTileControlAffinity.leading,
                          dense: true,
                        ),
                    ]),
                  ),
                if (!_completed) ...[
                  const SizedBox(height: 12),
                  Row(children: [
                    Expanded(
                      child: TextField(
                        controller: _newItem,
                        decoration: const InputDecoration(
                          hintText: 'Add an item…',
                          border: OutlineInputBorder(),
                          isDense: true,
                        ),
                        onSubmitted: (_) => _busy ? null : _addItem(),
                      ),
                    ),
                    IconButton(onPressed: _busy ? null : _addItem, icon: const Icon(Icons.add_circle)),
                  ]),
                  if (_error != null) ...[
                    const SizedBox(height: 12),
                    Text(_error!, style: const TextStyle(color: Colors.red)),
                  ],
                  const SizedBox(height: 20),
                  FilledButton.icon(
                    onPressed: _busy || _items.isEmpty ? null : _complete,
                    icon: const Icon(Icons.check),
                    label: const Text('Complete & sign off'),
                    style: FilledButton.styleFrom(padding: const EdgeInsets.symmetric(vertical: 14)),
                  ),
                ],
              ],
            ),
    );
  }
}

/// Create a new checklist of a chosen type (optionally seeded with items).
class _NewChecklistSheet extends StatefulWidget {
  const _NewChecklistSheet({required this.projectId});
  final String projectId;

  @override
  State<_NewChecklistSheet> createState() => _NewChecklistSheetState();
}

class _NewChecklistSheetState extends State<_NewChecklistSheet> {
  String _type = 'install';
  final _seed = TextEditingController();
  bool _busy = false;
  String? _error;

  Future<void> _create() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    final items = _seed.text
        .split('\n')
        .map((s) => s.trim())
        .where((s) => s.isNotEmpty)
        .toList();
    try {
      final c = await Services.i.data.createChecklist(widget.projectId, _type, items);
      if (mounted) Navigator.pop(context, c);
    } on ApiException catch (e) {
      setState(() {
        _error = e.message;
        _busy = false;
      });
    } catch (_) {
      setState(() {
        _error = 'Could not create the checklist.';
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
        const Text('New checklist', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
        const SizedBox(height: 16),
        DropdownButtonFormField<String>(
          value: _type,
          decoration: const InputDecoration(labelText: 'Type', border: OutlineInputBorder()),
          items: [for (final t in kChecklistTypes) DropdownMenuItem(value: t, child: Text(t))],
          onChanged: _busy ? null : (v) => setState(() => _type = v ?? _type),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _seed,
          maxLines: 4,
          decoration: const InputDecoration(
            labelText: 'Items (one per line, optional)',
            border: OutlineInputBorder(),
            alignLabelWithHint: true,
          ),
        ),
        if (_error != null) ...[
          const SizedBox(height: 10),
          Text(_error!, style: const TextStyle(color: Colors.red)),
        ],
        const SizedBox(height: 16),
        FilledButton(
          onPressed: _busy ? null : _create,
          style: FilledButton.styleFrom(padding: const EdgeInsets.symmetric(vertical: 14)),
          child: _busy
              ? const SizedBox(height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
              : const Text('Create'),
        ),
        TextButton(onPressed: _busy ? null : () => Navigator.pop(context), child: const Text('Cancel')),
      ]),
    );
  }
}
