import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:ij_core/ij_core.dart';

import '../services.dart';
import '../home/company_shell.dart';

/// Step 2 of login: enter the authenticator (TOTP) code or a backup code
/// (contract / MOBILE_SECURITY_STANDARDS Part 5).
class MfaChallengeScreen extends StatefulWidget {
  const MfaChallengeScreen({super.key, required this.mfaToken});
  final String mfaToken;

  @override
  State<MfaChallengeScreen> createState() => _MfaChallengeScreenState();
}

class _MfaChallengeScreenState extends State<MfaChallengeScreen> {
  final _code = TextEditingController();
  bool _busy = false;
  String? _error;

  Future<void> _verify() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await Services.i.auth.verifyMfa(widget.mfaToken, _code.text.trim());
      if (!mounted) return;
      Navigator.of(context).pushAndRemoveUntil(
        MaterialPageRoute(builder: (_) => const CompanyShell()),
        (_) => false,
      );
    } on ApiException catch (e) {
      setState(() {
        _error = e.statusCode == 401 ? 'This sign-in expired. Please start again.' : 'Invalid code';
        _busy = false;
      });
    } catch (_) {
      setState(() {
        _error = 'Something went wrong.';
        _busy = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Two-factor authentication')),
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              const Icon(Icons.verified_user_outlined, size: 48),
              const SizedBox(height: 12),
              const Text('Enter the 6-digit code from your authenticator app, or a backup code.',
                  textAlign: TextAlign.center, style: TextStyle(color: Colors.black54)),
              const SizedBox(height: 20),
              TextField(
                controller: _code,
                autofocus: true,
                keyboardType: TextInputType.number,
                inputFormatters: [FilteringTextInputFormatter.allow(RegExp(r'[0-9a-fA-F]'))],
                decoration: const InputDecoration(labelText: 'Code', border: OutlineInputBorder()),
                onSubmitted: (_) => _busy ? null : _verify(),
              ),
              if (_error != null) ...[
                const SizedBox(height: 12),
                Text(_error!, style: const TextStyle(color: Colors.red)),
              ],
              const SizedBox(height: 20),
              FilledButton(
                onPressed: _busy ? null : _verify,
                style: FilledButton.styleFrom(padding: const EdgeInsets.symmetric(vertical: 16)),
                child: _busy
                    ? const SizedBox(height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                    : const Text('Verify'),
              ),
            ]),
          ),
        ),
      ),
    );
  }
}

/// Enable / view MFA (from the shell). Shows status; enrolls with an
/// authenticator secret and one-time backup codes.
class MfaEnrollScreen extends StatefulWidget {
  const MfaEnrollScreen({super.key});

  @override
  State<MfaEnrollScreen> createState() => _MfaEnrollScreenState();
}

class _MfaEnrollScreenState extends State<MfaEnrollScreen> {
  late Future<Map<String, dynamic>> _status;
  Map<String, dynamic>? _enroll; // {secret, otpauth_uri}
  final _code = TextEditingController();
  List<String>? _backupCodes;
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _status = Services.i.auth.mfaStatus();
  }

  Future<void> _startEnroll() async {
    setState(() { _busy = true; _error = null; });
    try {
      final e = await Services.i.auth.mfaEnroll();
      setState(() => _enroll = e);
    } catch (e) {
      setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _activate() async {
    setState(() { _busy = true; _error = null; });
    try {
      final codes = await Services.i.auth.mfaActivate(_code.text.trim());
      setState(() => _backupCodes = codes);
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } catch (_) {
      setState(() => _error = 'Could not enable MFA.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Two-factor authentication')),
      body: FutureBuilder<Map<String, dynamic>>(
        future: _status,
        builder: (context, snap) {
          if (!snap.hasData) return const Center(child: CircularProgressIndicator());
          final enrolled = snap.data!['enrolled'] == true;
          if (enrolled && _backupCodes == null) {
            return Padding(
              padding: const EdgeInsets.all(24),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Row(children: [Icon(Icons.check_circle, color: Color(0xFF4A5D23)), SizedBox(width: 8),
                  Text('MFA is enabled', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700))]),
                const SizedBox(height: 8),
                Text('Backup codes remaining: ${snap.data!['backup_codes_remaining'] ?? '—'}',
                    style: const TextStyle(color: Colors.black54)),
              ]),
            );
          }
          if (_backupCodes != null) return _backupView();
          return _enrollView();
        },
      ),
    );
  }

  Widget _enrollView() {
    return ListView(padding: const EdgeInsets.all(20), children: [
      const Text('Protect your account with an authenticator app',
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
      const SizedBox(height: 8),
      const Text('Use Google Authenticator, Microsoft Authenticator, or Authy.',
          style: TextStyle(color: Colors.black54)),
      const SizedBox(height: 20),
      if (_enroll == null)
        FilledButton(
          onPressed: _busy ? null : _startEnroll,
          style: FilledButton.styleFrom(padding: const EdgeInsets.symmetric(vertical: 14)),
          child: const Text('Enable MFA'),
        )
      else ...[
        const Text('1. Add this key to your authenticator app:', style: TextStyle(fontWeight: FontWeight.w600)),
        const SizedBox(height: 8),
        Card(
          child: ListTile(
            title: SelectableText(_enroll!['secret']?.toString() ?? '',
                style: const TextStyle(fontFamily: 'monospace', letterSpacing: 1.5)),
            trailing: IconButton(
              icon: const Icon(Icons.copy),
              onPressed: () => Clipboard.setData(ClipboardData(text: _enroll!['secret']?.toString() ?? '')),
            ),
          ),
        ),
        const SizedBox(height: 6),
        const Text('(A QR of this key can be shown here with a QR widget — the manual key works in every app.)',
            style: TextStyle(color: Colors.black38, fontSize: 12)),
        const SizedBox(height: 16),
        const Text('2. Enter the 6-digit code it shows:', style: TextStyle(fontWeight: FontWeight.w600)),
        const SizedBox(height: 8),
        TextField(
          controller: _code,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(labelText: 'Code', border: OutlineInputBorder()),
        ),
        if (_error != null) ...[
          const SizedBox(height: 12),
          Text(_error!, style: const TextStyle(color: Colors.red)),
        ],
        const SizedBox(height: 16),
        FilledButton(
          onPressed: _busy ? null : _activate,
          style: FilledButton.styleFrom(padding: const EdgeInsets.symmetric(vertical: 14)),
          child: _busy
              ? const SizedBox(height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
              : const Text('Turn on MFA'),
        ),
      ],
    ]);
  }

  Widget _backupView() {
    return ListView(padding: const EdgeInsets.all(20), children: [
      const Row(children: [Icon(Icons.check_circle, color: Color(0xFF4A5D23)), SizedBox(width: 8),
        Text('MFA enabled', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700))]),
      const SizedBox(height: 12),
      const Text('Save these backup codes somewhere safe — each works once if you lose your authenticator.',
          style: TextStyle(color: Colors.black54)),
      const SizedBox(height: 12),
      Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Wrap(spacing: 20, runSpacing: 8, children: [
            for (final c in _backupCodes!) SelectableText(c, style: const TextStyle(fontFamily: 'monospace', fontSize: 15)),
          ]),
        ),
      ),
      const SizedBox(height: 16),
      FilledButton.tonal(
        onPressed: () => Clipboard.setData(ClipboardData(text: _backupCodes!.join('\n'))),
        child: const Text('Copy codes'),
      ),
      const SizedBox(height: 8),
      FilledButton(onPressed: () => Navigator.pop(context), child: const Text('Done')),
    ]);
  }
}
