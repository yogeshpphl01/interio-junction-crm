import 'package:flutter/material.dart';
import 'package:ij_core/ij_core.dart';

import '../services.dart';
import '../widgets.dart';

/// Chat with the Interio Junction project team. A customer sees only the thread
/// belonging to their own project — the backend resolves the thread from their
/// session, so there is no way to open somebody else's conversation.
class ChatTab extends StatefulWidget {
  const ChatTab({super.key});

  @override
  State<ChatTab> createState() => _ChatTabState();
}

class _ChatTabState extends State<ChatTab> {
  final _data = Services.i.data;
  final _input = TextEditingController();
  final _scroll = ScrollController();

  bool _loading = true;
  bool _sending = false;
  String? _error;
  String? _threadId;
  List<Map<String, dynamic>> _messages = const [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      var id = _threadId;
      if (id == null) {
        final threads = await _data.chatThreads();
        if (threads.isEmpty) {
          if (!mounted) return;
          setState(() {
            _loading = false;
            _threadId = null;
            _messages = const [];
          });
          return;
        }
        id = threads.first['id'].toString();
      }
      final msgs = await _data.chatMessages(id);
      if (!mounted) return;
      setState(() {
        _threadId = id;
        _messages = msgs;
        _loading = false;
      });
      _jumpToEnd();
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message;
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _error = 'Could not load messages.';
        _loading = false;
      });
    }
  }

  void _jumpToEnd() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.jumpTo(_scroll.position.maxScrollExtent);
      }
    });
  }

  Future<void> _send() async {
    final text = _input.text.trim();
    final id = _threadId;
    if (text.isEmpty || id == null || _sending) return;
    setState(() => _sending = true);
    try {
      await _data.sendChatMessage(id, text);
      _input.clear();
      final msgs = await _data.chatMessages(id);
      if (!mounted) return;
      setState(() {
        _messages = msgs;
        _sending = false;
      });
      _jumpToEnd();
    } catch (_) {
      if (!mounted) return;
      setState(() => _sending = false);
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('Message not sent. Please try again.')));
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());

    if (_error != null) {
      return ListView(children: [
        const SizedBox(height: 140),
        const Icon(Icons.error_outline, size: 48, color: Colors.black26),
        const SizedBox(height: 12),
        Text(_error!, textAlign: TextAlign.center, style: const TextStyle(color: Colors.black54)),
        const SizedBox(height: 12),
        Center(child: FilledButton.tonal(onPressed: _load, child: const Text('Retry'))),
      ]);
    }

    if (_threadId == null) {
      return const EmptyState(
        icon: Icons.chat_bubble_outline,
        text: 'No conversation yet.\nA chat opens once your project starts.',
      );
    }

    return Column(
      children: [
        Expanded(
          child: _messages.isEmpty
              ? const EmptyState(
                  icon: Icons.chat_bubble_outline,
                  text: 'No messages yet.\nSay hello to your project team.',
                )
              : RefreshIndicator(
                  onRefresh: _load,
                  child: ListView.builder(
                    controller: _scroll,
                    padding: const EdgeInsets.fromLTRB(12, 12, 12, 8),
                    itemCount: _messages.length,
                    itemBuilder: (_, i) => _Bubble(_messages[i]),
                  ),
                ),
        ),
        const Divider(height: 1),
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 8, 8, 10),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Expanded(
                child: TextField(
                  controller: _input,
                  minLines: 1,
                  maxLines: 4,
                  textCapitalization: TextCapitalization.sentences,
                  decoration: const InputDecoration(
                    hintText: 'Write a message…',
                    border: OutlineInputBorder(),
                    isDense: true,
                    contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 12),
                  ),
                  onSubmitted: (_) => _send(),
                ),
              ),
              const SizedBox(width: 6),
              IconButton.filled(
                onPressed: _sending ? null : _send,
                icon: _sending
                    ? const SizedBox(
                        height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.send),
                tooltip: 'Send',
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _Bubble extends StatelessWidget {
  const _Bubble(this.m);
  final Map<String, dynamic> m;

  @override
  Widget build(BuildContext context) {
    final mine = m['sender_type']?.toString() == 'customer';
    final scheme = Theme.of(context).colorScheme;
    return Align(
      alignment: mine ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 9),
        constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.78),
        decoration: BoxDecoration(
          color: mine ? scheme.primary.withAlpha(28) : Colors.black.withAlpha(12),
          borderRadius: BorderRadius.only(
            topLeft: const Radius.circular(14),
            topRight: const Radius.circular(14),
            bottomLeft: Radius.circular(mine ? 14 : 3),
            bottomRight: Radius.circular(mine ? 3 : 14),
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (!mine)
              Padding(
                padding: const EdgeInsets.only(bottom: 3),
                child: Text(
                  m['sender_name']?.toString() ?? 'Interio Junction',
                  style: TextStyle(
                      fontSize: 11, fontWeight: FontWeight.w700, color: scheme.primary),
                ),
              ),
            Text(m['body']?.toString() ?? ''),
            const SizedBox(height: 3),
            Text(_time(m['created_at']),
                style: const TextStyle(fontSize: 10, color: Colors.black45)),
          ],
        ),
      ),
    );
  }

  String _time(dynamic iso) {
    if (iso == null) return '';
    final s = iso.toString();
    // "2026-07-20T10:00:00Z" -> "20 Jul, 10:00"
    if (s.length >= 16) {
      final date = s.substring(0, 10);
      final hm = s.substring(11, 16);
      return '$date · $hm';
    }
    return s;
  }
}
