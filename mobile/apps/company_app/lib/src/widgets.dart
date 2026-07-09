import 'package:flutter/material.dart';

/// Indian-grouped rupee formatting: 590000 -> "₹5,90,000".
String inr(num? v) {
  if (v == null) return '—';
  final neg = v < 0;
  final digits = v.abs().round().toString();
  String grouped;
  if (digits.length <= 3) {
    grouped = digits;
  } else {
    final last3 = digits.substring(digits.length - 3);
    var rest = digits.substring(0, digits.length - 3);
    final parts = <String>[];
    while (rest.length > 2) {
      parts.insert(0, rest.substring(rest.length - 2));
      rest = rest.substring(0, rest.length - 2);
    }
    if (rest.isNotEmpty) parts.insert(0, rest);
    grouped = '${parts.join(',')},$last3';
  }
  return '₹${neg ? '-' : ''}$grouped';
}

/// Loads a future with spinner/error/empty + pull-to-refresh. The builder gets
/// the data and a `refresh` callback to call after a mutating action.
class AsyncRefresh<T> extends StatefulWidget {
  const AsyncRefresh({super.key, required this.load, required this.onData});

  final Future<T> Function() load;
  final Widget Function(T data, Future<void> Function() refresh) onData;

  @override
  State<AsyncRefresh<T>> createState() => _AsyncRefreshState<T>();
}

class _AsyncRefreshState<T> extends State<AsyncRefresh<T>> {
  late Future<T> _future = widget.load();

  Future<void> _refresh() async {
    final next = widget.load();
    setState(() => _future = next);
    await next;
  }

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: _refresh,
      child: FutureBuilder<T>(
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
              Text('${snap.error}',
                  textAlign: TextAlign.center, style: const TextStyle(color: Colors.black54)),
              const SizedBox(height: 12),
              Center(child: FilledButton.tonal(onPressed: _refresh, child: const Text('Retry'))),
            ]);
          }
          return widget.onData(snap.data as T, _refresh);
        },
      ),
    );
  }
}

class EmptyState extends StatelessWidget {
  const EmptyState({super.key, required this.icon, required this.text});
  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    return ListView(children: [
      const SizedBox(height: 140),
      Icon(icon, size: 56, color: Colors.black26),
      const SizedBox(height: 16),
      Text(text, textAlign: TextAlign.center, style: const TextStyle(color: Colors.black54)),
    ]);
  }
}

class StatusChip extends StatelessWidget {
  const StatusChip(this.label, {super.key, this.color});
  final String label;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final c = color ?? Theme.of(context).colorScheme.primary;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
      decoration: BoxDecoration(color: c.withOpacity(0.14), borderRadius: BorderRadius.circular(20)),
      child: Text(label, style: TextStyle(color: c, fontWeight: FontWeight.w600, fontSize: 12)),
    );
  }
}
