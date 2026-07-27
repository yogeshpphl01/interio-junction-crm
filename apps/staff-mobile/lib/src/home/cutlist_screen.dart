import 'package:flutter/material.dart';
import 'package:ij_core/ij_core.dart';

import '../services.dart';

/// Ingest an Infurnia cut list into a project (contract §5.5). Interim manual
/// path: paste the exported rows (one part per line). A file/PDF parser for the
/// Infurnia export can replace the parser here without touching the API call.
class CutlistIngestScreen extends StatefulWidget {
  const CutlistIngestScreen({super.key, required this.projectId, this.projectCode});
  final String projectId;
  final String? projectCode;

  @override
  State<CutlistIngestScreen> createState() => _CutlistIngestScreenState();
}

class _CutlistIngestScreenState extends State<CutlistIngestScreen> {
  final _ref = TextEditingController();
  final _rows = TextEditingController();
  bool _busy = false;
  String? _error;
  String? _result;

  /// One part per line: `part_id, name, material, dimensions`. Only the part id
  /// is required; the id doubles as the QR value unless the label prints another.
  List<Map<String, dynamic>> _parse(String text) {
    final out = <Map<String, dynamic>>[];
    for (final line in text.split('\n')) {
      final t = line.trim();
      if (t.isEmpty) continue;
      final cols = t.split(',').map((s) => s.trim()).toList();
      if (cols.isEmpty || cols.first.isEmpty) continue;
      out.add({
        'part_uid': cols[0],
        if (cols.length > 1 && cols[1].isNotEmpty) 'name': cols[1],
        if (cols.length > 2 && cols[2].isNotEmpty) 'material': cols[2],
        if (cols.length > 3 && cols[3].isNotEmpty) 'dimensions': cols[3],
        'qr_value': cols[0],
      });
    }
    return out;
  }

  int get _parsedCount => _parse(_rows.text).length;

  Future<void> _import() async {
    final parts = _parse(_rows.text);
    if (parts.isEmpty) {
      setState(() => _error = 'Add at least one part (part id per line).');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
      _result = null;
    });
    try {
      final res = await Services.i.data.ingestCutlist(
        projectId: widget.projectId,
        infurniaRef: _ref.text.trim().isEmpty ? null : _ref.text.trim(),
        parts: parts,
      );
      if (!mounted) return;
      setState(() {
        _result = 'Imported ${res['created']} part(s)'
            '${(res['skipped'] ?? 0) > 0 ? ', skipped ${res['skipped']} already-known' : ''}.';
        _busy = false;
        _rows.clear();
      });
    } on ApiException catch (e) {
      setState(() {
        _error = e.statusCode == 403 ? 'You do not have permission to ingest cut lists.' : e.message;
        _busy = false;
      });
    } catch (_) {
      setState(() {
        _error = 'Import failed.';
        _busy = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(widget.projectCode == null
          ? 'Import cut list'
          : 'Import cut list · ${widget.projectCode}')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const Text('Paste the Infurnia cut-list rows — one part per line:',
              style: TextStyle(fontWeight: FontWeight.w600)),
          const SizedBox(height: 4),
          const Text('part id, name, material, dimensions',
              style: TextStyle(color: Colors.black54, fontFamily: 'monospace')),
          const SizedBox(height: 12),
          TextField(
            controller: _ref,
            decoration: const InputDecoration(
              labelText: 'Infurnia reference (optional)',
              border: OutlineInputBorder(),
              isDense: true,
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _rows,
            maxLines: 10,
            onChanged: (_) => setState(() {}),
            decoration: const InputDecoration(
              hintText: 'PNL-000123, Base side L, 18mm HDHMR, 720x560\n'
                  'PNL-000124, Base side R, 18mm HDHMR, 720x560',
              border: OutlineInputBorder(),
              alignLabelWithHint: true,
            ),
            style: const TextStyle(fontFamily: 'monospace', fontSize: 13),
          ),
          const SizedBox(height: 8),
          Text('$_parsedCount part(s) detected', style: const TextStyle(color: Colors.black54)),
          if (_error != null) ...[
            const SizedBox(height: 12),
            Text(_error!, style: const TextStyle(color: Colors.red)),
          ],
          if (_result != null) ...[
            const SizedBox(height: 12),
            Text(_result!, style: const TextStyle(color: Color(0xFF4A5D23), fontWeight: FontWeight.w600)),
          ],
          const SizedBox(height: 16),
          FilledButton.icon(
            onPressed: _busy || _parsedCount == 0 ? null : _import,
            icon: const Icon(Icons.upload_file),
            label: Text(_busy ? 'Importing…' : 'Import $_parsedCount part(s)'),
            style: FilledButton.styleFrom(padding: const EdgeInsets.symmetric(vertical: 14)),
          ),
        ],
      ),
    );
  }
}
