import 'dart:convert';
import 'package:flutter/material.dart';

import '../services.dart';
import '../widgets.dart';
import '../auth/otp_login_screen.dart';

/// DPDP privacy & consent for the customer (mirrors the web portal):
///   • view/withdraw itemized consents (necessary shown locked; optional toggles)
///   • change email / phone, verified by a one-time code to the new value
///   • download a copy of my data (right to access)
///   • delete my data — enquiry-only erases now; project clients are queued
class PrivacyScreen extends StatefulWidget {
  const PrivacyScreen({super.key});

  @override
  State<PrivacyScreen> createState() => _PrivacyScreenState();
}

class _PrivacyScreenState extends State<PrivacyScreen> {
  final _data = Services.i.data;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Privacy & consent')),
      body: AsyncRefresh<Map<String, dynamic>>(
        load: _data.consent,
        onData: (data, refresh) {
          final catalog = (data['catalog'] as Map?)?.cast<String, dynamic>() ?? const {};
          final current = (data['current'] as Map?)?.cast<String, dynamic>() ?? const {};
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              const _SectionTitle('How we use your data'),
              Card(
                child: Column(
                  children: [
                    for (final entry in catalog.entries)
                      _consentTile(entry.key, (entry.value as Map).cast<String, dynamic>(),
                          current[entry.key] == true, refresh),
                  ],
                ),
              ),
              Padding(
                padding: const EdgeInsets.only(top: 8, left: 4),
                child: Text('Policy version ${data['policy_version'] ?? ''}. Your choices are logged.',
                    style: const TextStyle(color: Colors.black45, fontSize: 12)),
              ),
              const SizedBox(height: 20),
              const _SectionTitle('Your details'),
              Card(
                child: Column(children: [
                  ListTile(
                    leading: const Icon(Icons.email_outlined),
                    title: const Text('Email'),
                    trailing: TextButton(onPressed: () => _changeContact('email'), child: const Text('Change')),
                  ),
                  const Divider(height: 1),
                  ListTile(
                    leading: const Icon(Icons.phone_outlined),
                    title: const Text('Phone'),
                    trailing: TextButton(onPressed: () => _changeContact('phone'), child: const Text('Change')),
                  ),
                ]),
              ),
              const SizedBox(height: 20),
              const _SectionTitle('Your data'),
              Card(
                child: Column(children: [
                  ListTile(
                    leading: const Icon(Icons.download_outlined),
                    title: const Text('Download a copy of my data'),
                    subtitle: const Text('Everything we hold about you.'),
                    onTap: _export,
                  ),
                  const Divider(height: 1),
                  ListTile(
                    leading: const Icon(Icons.delete_outline, color: Colors.red),
                    title: const Text('Delete my data', style: TextStyle(color: Colors.red)),
                    subtitle: const Text('If you only enquired, deleted now. If you have a project, kept for warranty/legal and your request is logged.'),
                    isThreeLine: true,
                    onTap: _delete,
                  ),
                ]),
              ),
              const SizedBox(height: 24),
              const Padding(
                padding: EdgeInsets.symmetric(horizontal: 8),
                child: Text(
                  'Questions or a privacy concern? Contact our team. You may also complain to the Data Protection Board of India.',
                  style: TextStyle(color: Colors.black45, fontSize: 12),
                  textAlign: TextAlign.center,
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  Widget _consentTile(String key, Map<String, dynamic> p, bool on, Future<void> Function() refresh) {
    final necessary = p['category'] == 'necessary';
    return SwitchListTile(
      value: necessary ? true : on,
      onChanged: necessary
          ? null
          : (v) async {
              try {
                await _data.setConsent(key, v);
                await refresh();
              } catch (_) {
                _snack('Could not update');
              }
            },
      title: Text(p['label']?.toString() ?? key),
      subtitle: Text([
        p['description']?.toString(),
        if (necessary) 'Required',
      ].whereType<String>().join('\n')),
      isThreeLine: true,
    );
  }

  Future<void> _changeContact(String field) async {
    final valueCtl = TextEditingController();
    final newValue = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Change $field'),
        content: TextField(
          controller: valueCtl,
          keyboardType: field == 'email' ? TextInputType.emailAddress : TextInputType.phone,
          decoration: InputDecoration(hintText: field == 'email' ? 'new@email.com' : 'New 10-digit number'),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, valueCtl.text.trim()), child: const Text('Send code')),
        ],
      ),
    );
    if (newValue == null || newValue.isEmpty) return;
    try {
      await _data.changeContactStart(field, newValue);
    } catch (_) {
      _snack('Could not send code');
      return;
    }
    if (!mounted) return;
    final codeCtl = TextEditingController();
    final code = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Verify new $field'),
        content: TextField(
          controller: codeCtl,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(hintText: 'Enter the code we sent'),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, codeCtl.text.trim()), child: const Text('Verify')),
        ],
      ),
    );
    if (code == null || code.isEmpty) return;
    try {
      await _data.changeContactVerify(field, code);
      _snack('${field[0].toUpperCase()}${field.substring(1)} updated');
    } catch (_) {
      _snack('Could not verify');
    }
  }

  Future<void> _export() async {
    try {
      final data = await _data.exportData();
      if (!mounted) return;
      showDialog<void>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('Your data'),
          content: SizedBox(
            width: double.maxFinite,
            child: SingleChildScrollView(
              child: SelectableText(const JsonEncoder.withIndent('  ').convert(data)),
            ),
          ),
          actions: [TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Close'))],
        ),
      );
    } catch (_) {
      _snack('Could not export');
    }
  }

  Future<void> _delete() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete my data?'),
        content: const Text(
            "This can't be undone. If you only enquired, your data is deleted now and you'll be signed out. "
            'If you have a project, we keep records for the warranty/legal period and log your request.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Colors.red),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (ok != true) return;
    try {
      final res = await _data.requestErasure(reason: 'customer requested via app');
      if (!mounted) return;
      if (res['status'] == 'erased') {
        _snack('Your data has been deleted.');
        await Services.i.auth.logout();
        if (!mounted) return;
        Navigator.of(context).pushAndRemoveUntil(
          MaterialPageRoute(builder: (_) => const OtpLoginScreen()),
          (_) => false,
        );
      } else {
        _snack(res['message']?.toString() ?? 'Request received.');
      }
    } catch (_) {
      _snack('Could not process request');
    }
  }

  void _snack(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle(this.text);
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(left: 4, bottom: 8),
        child: Text(text, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
      );
}
