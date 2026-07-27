import 'package:flutter/material.dart';

import '../services.dart';
import '../widgets.dart';

/// Designs tab: the customer's shared design revisions (contract §4.5).
class DesignsTab extends StatelessWidget {
  const DesignsTab({super.key});

  @override
  Widget build(BuildContext context) {
    return AsyncRefresh<List<Map<String, dynamic>>>(
      load: Services.i.data.designs,
      onData: (designs, refresh) {
        if (designs.isEmpty) {
          return const EmptyState(
            icon: Icons.view_in_ar_outlined,
            text: 'No designs shared yet.\nYour 3D designs will appear here.',
          );
        }
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            for (final d in designs)
              Card(
                margin: const EdgeInsets.only(bottom: 12),
                child: ListTile(
                  leading: const Icon(Icons.view_in_ar),
                  title: Text(d['title']?.toString() ?? 'Design R${d['revision_number'] ?? '?'}',
                      style: const TextStyle(fontWeight: FontWeight.w600)),
                  subtitle: Text('R${d['revision_number'] ?? '?'} · '
                      '${((d['documents'] as List?) ?? const []).length} file(s)'),
                  trailing: _revChip(d['status'] as String?),
                  onTap: () async {
                    final changed = await Navigator.of(context).push<bool>(
                      MaterialPageRoute(builder: (_) => DesignDetailScreen(design: d)),
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

Widget _revChip(String? status) {
  switch (status) {
    case 'Approved':
      return const StatusChip('Approved', color: Color(0xFF4A5D23));
    case 'Revision Requested':
      return const StatusChip('Changes asked', color: Color(0xFFA95A3F));
    default:
      return const StatusChip('For review', color: Color(0xFFC99A4B));
  }
}

class DesignDetailScreen extends StatefulWidget {
  const DesignDetailScreen({super.key, required this.design});
  final Map<String, dynamic> design;

  @override
  State<DesignDetailScreen> createState() => _DesignDetailScreenState();
}

class _DesignDetailScreenState extends State<DesignDetailScreen> {
  bool _busy = false;
  late String _status = widget.design['status'] as String? ?? '';

  Future<void> _run(Future<void> Function() action, String okMsg, String newStatus) async {
    setState(() => _busy = true);
    try {
      await action();
      if (!mounted) return;
      setState(() => _status = newStatus);
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(okMsg)));
      Navigator.pop(context, true);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
        setState(() => _busy = false);
      }
    }
  }

  Future<void> _approve() =>
      _run(() => Services.i.data.approveDesign(widget.design['id'] as String),
          'Design approved ✓', 'Approved');

  Future<void> _requestChanges() async {
    final controller = TextEditingController();
    final feedback = await showDialog<String>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Request changes'),
        content: TextField(
          controller: controller,
          autofocus: true,
          maxLines: 3,
          decoration: const InputDecoration(
            hintText: 'What would you like changed?',
            border: OutlineInputBorder(),
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.pop(context, controller.text.trim()),
              child: const Text('Send')),
        ],
      ),
    );
    if (feedback == null) return;
    await _run(
      () => Services.i.data.requestDesignChanges(widget.design['id'] as String, feedback),
      'Sent to your designer', 'Revision Requested',
    );
  }

  @override
  Widget build(BuildContext context) {
    final d = widget.design;
    final docs = ((d['documents'] as List?) ?? const []).cast<Map<String, dynamic>>();
    final feedback = (d['client_feedback'] as String?)?.trim() ?? '';
    return Scaffold(
      appBar: AppBar(title: Text(d['title']?.toString() ?? 'Design')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Row(children: [_revChip(_status)]),
          const SizedBox(height: 16),
          if (docs.isEmpty)
            const Card(child: ListTile(leading: Icon(Icons.image_not_supported_outlined), title: Text('No files attached')))
          else
            Card(
              child: Column(children: [
                for (final doc in docs)
                  ListTile(
                    leading: const Icon(Icons.insert_drive_file_outlined),
                    title: Text(doc['filename']?.toString() ?? doc['type']?.toString() ?? 'File'),
                    subtitle: Text(doc['type']?.toString() ?? ''),
                    // A signed download URL from storage_path is wired when object storage is on.
                  ),
              ]),
            ),
          if (feedback.isNotEmpty) ...[
            const SizedBox(height: 16),
            Card(
              color: const Color(0xFFFBF0EA),
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  const Text('Your feedback', style: TextStyle(fontWeight: FontWeight.w700)),
                  const SizedBox(height: 6),
                  Text(feedback),
                ]),
              ),
            ),
          ],
          const SizedBox(height: 24),
          if (_status != 'Approved')
            FilledButton.icon(
              onPressed: _busy ? null : _approve,
              icon: const Icon(Icons.check),
              label: const Text('Approve design'),
              style: FilledButton.styleFrom(padding: const EdgeInsets.symmetric(vertical: 16)),
            ),
          const SizedBox(height: 10),
          OutlinedButton.icon(
            onPressed: _busy ? null : _requestChanges,
            icon: const Icon(Icons.edit_outlined),
            label: const Text('Request changes'),
            style: OutlinedButton.styleFrom(padding: const EdgeInsets.symmetric(vertical: 16)),
          ),
          if (_busy) const Padding(padding: EdgeInsets.only(top: 16), child: Center(child: CircularProgressIndicator())),
        ],
      ),
    );
  }
}
