import 'package:flutter/material.dart';
import 'package:ij_core/ij_core.dart';

import '../services.dart';
import '../home/home_shell.dart';

/// Two-step phone + OTP login (contract §4.1).
class OtpLoginScreen extends StatefulWidget {
  const OtpLoginScreen({super.key});

  @override
  State<OtpLoginScreen> createState() => _OtpLoginScreenState();
}

class _OtpLoginScreenState extends State<OtpLoginScreen> with SecureScreenMixin {
  final _phone = TextEditingController();
  final _code = TextEditingController();
  bool _codeSent = false;
  bool _busy = false;
  String? _error;

  Future<void> _run(Future<void> Function() action) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await action();
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } catch (_) {
      setState(() => _error = 'Something went wrong. Please try again.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _requestOtp() => _run(() async {
        await Services.i.auth.requestOtp(_phone.text.trim());
        setState(() => _codeSent = true);
      });

  Future<void> _verify() => _run(() async {
        await Services.i.auth.verifyOtp(_phone.text.trim(), _code.text.trim());
        if (!mounted) return;
        Navigator.of(context).pushReplacement(
          MaterialPageRoute(builder: (_) => const HomeShell()),
        );
      });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Text('Interio Junction',
                      textAlign: TextAlign.center,
                      style: TextStyle(fontSize: 28, fontWeight: FontWeight.w700)),
                  const SizedBox(height: 8),
                  Text(
                    _codeSent
                        ? 'Enter the code we sent to ${_phone.text.trim()}'
                        : 'Sign in with your phone number',
                    textAlign: TextAlign.center,
                    style: const TextStyle(color: Colors.black54),
                  ),
                  const SizedBox(height: 28),
                  if (!_codeSent)
                    TextField(
                      controller: _phone,
                      keyboardType: TextInputType.phone,
                      decoration: const InputDecoration(
                        labelText: 'Phone number',
                        hintText: '+91 90000 12345',
                        border: OutlineInputBorder(),
                      ),
                    )
                  else
                    TextField(
                      controller: _code,
                      keyboardType: TextInputType.number,
                      autofocus: true,
                      // Keyboard-cache hygiene for the one-time code (MASVS-STORAGE
                      // C4): don't let the OTP land in autofill / suggestion history.
                      enableSuggestions: false,
                      autocorrect: false,
                      enableIMEPersonalizedLearning: false,
                      decoration: const InputDecoration(
                        labelText: 'Login code',
                        hintText: '4-digit code',
                        border: OutlineInputBorder(),
                      ),
                    ),
                  if (_error != null) ...[
                    const SizedBox(height: 12),
                    Text(_error!, style: const TextStyle(color: Colors.red)),
                  ],
                  const SizedBox(height: 20),
                  FilledButton(
                    onPressed: _busy ? null : (_codeSent ? _verify : _requestOtp),
                    style: FilledButton.styleFrom(
                        padding: const EdgeInsets.symmetric(vertical: 16)),
                    child: _busy
                        ? const SizedBox(
                            height: 20,
                            width: 20,
                            child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                        : Text(_codeSent ? 'Verify & continue' : 'Send code'),
                  ),
                  if (_codeSent)
                    TextButton(
                      onPressed: _busy ? null : () => setState(() => _codeSent = false),
                      child: const Text('Change number'),
                    ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
