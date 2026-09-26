import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:ij_core/ij_core.dart';
import 'package:url_launcher/url_launcher.dart';

import '../services.dart';
import '../widgets.dart';

/// Documents the customer is allowed to see — renders, drawings, quotations,
/// site photos. The file bytes are never served straight from the list: tapping
/// a row asks the backend for a short-lived **signed link** and opens that, so a
/// document can only be fetched by someone who just proved they own it.
class DocumentsScreen extends StatefulWidget {
  const DocumentsScreen({super.key});

  @override
  State<DocumentsScreen> createState() => _DocumentsScreenState();
}

class _DocumentsScreenState extends State<DocumentsScreen> {
  final _data = Services.i.data;
  String? _busyId;

  Future<void> _open(Map<String, dynamic> doc) async {
    final id = doc['id'].toString();
    setState(() => _busyId = id);
    try {
      final url = await _data.documentDownloadUrl(id);
      final uri = Uri.parse(url);
      final opened = await launchUrl(uri, mode: LaunchMode.externalApplication);
      if (!opened) {
        await Clipboard.setData(ClipboardData(text: url));
        _snack('Could not open it here — the link is copied to your clipboard.');
      }
    } on ApiException catch (e) {
      _snack(e.message);
    } catch (_) {
      _snack('Could not open that document.');
    } finally {
      if (mounted) setState(() => _busyId = null);
    }
  }

  void _snack(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Documents')),
      body: AsyncRefresh<List<Map<String, dynamic>>>(
        load: _data.documents,
        onData: (docs, refresh) {
          if (docs.isEmpty) {
            return const EmptyState(
              icon: Icons.folder_open_outlined,
              text: 'No documents yet.\nDrawings and quotations will appear here.',
            );
          }
          return ListView.separated(
            padding: const EdgeInsets.symmetric(vertical: 8),
            itemCount: docs.length,
            separatorBuilder: (_, __) => const Divider(height: 1),
            itemBuilder: (_, i) {
              final d = docs[i];
              final id = d['id'].toString();
              return ListTile(
                leading: Icon(_iconFor(d['content_type']?.toString()), color: Colors.black54),
                title: Text(d['filename']?.toString() ?? 'Document'),
                subtitle: Text([
                  d['type']?.toString(),
                  _size(d['size']),
                  _date(d['created_at']),
                ].whereType<String>().join(' · ')),
                trailing: _busyId == id
                    ? const SizedBox(
                        height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.open_in_new, size: 18),
                onTap: _busyId == null ? () => _open(d) : null,
              );
            },
          );
        },
      ),
    );
  }

  IconData _iconFor(String? contentType) {
    final t = contentType ?? '';
    if (t.startsWith('image/')) return Icons.image_outlined;
    if (t.contains('pdf')) return Icons.picture_as_pdf_outlined;
    return Icons.insert_drive_file_outlined;
  }

  String? _size(dynamic bytes) {
    if (bytes is! num) return null;
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(0)} KB';
    return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
  }

  String? _date(dynamic iso) {
    if (iso == null) return null;
    final s = iso.toString();
    return s.length >= 10 ? s.substring(0, 10) : s;
  }
}
