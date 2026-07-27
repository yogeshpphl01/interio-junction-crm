import 'package:flutter/material.dart';
import 'package:ij_core/ij_core.dart';

import '../services.dart';

/// Change-password for the signed-in employee (item 11).
///
/// Normal path: prove the current password and set a new one. After three wrong
/// tries the server locks this path (HTTP 423); we then switch to a reset flow
/// that sends a one-time code to the account's recovery email AND phone, which
/// the user enters here with a new password. A "Forgot your current password?"
/// link starts that same reset flow on demand.
class ChangePasswordScreen extends StatefulWidget {
  const ChangePasswordScreen({super.key});

  @override
  State<ChangePasswordScreen> createState() => _ChangePasswordScreenState();
}

class _ChangePasswordScreenState extends State<ChangePasswordScreen> {
  final _current = TextEditingController();
  final _next = TextEditingController();
  final _confirm = TextEditingController();
  final _otp = TextEditingController();

  bool _resetMode = false;
  bool _busy = false;
  String? _error;
  String _sentTo = '';

  @override
  void dispose() {
    _current.dispose();
    _next.dispose();
    _confirm.dispose();
    _otp.dispose();
    super.dispose();
  }

  bool _validNew() {
    if (_next.text.length < 8) {
      setState(() => _error = 'New password must be at least 8 characters');
      return false;
    }
    if (_next.text != _confirm.text) {
      setState(() => _error = 'New passwords do not match');
      return false;
    }
    return true;
  }

  Future<void> _change() async {
    setState(() => _error = null);
    if (!_validNew()) return;
    setState(() => _busy = true);
    try {
      await Services.i.auth.changePassword(_current.text, _next.text);
      _done('Password changed');
    } on ApiException catch (e) {
      if (e.statusCode == 423) {
        // Locked → move straight into the email+phone OTP reset.
        await _startReset(note: 'Too many attempts. We\'ve sent a one-time code instead.');
      } else {
        setState(() {
          _error = e.message;
          _busy = false;
        });
      }
    } catch (_) {
      setState(() {
        _error = 'Could not change password';
        _busy = false;
      });
    }
  }

  Future<void> _startReset({String? note}) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final res = await Services.i.auth.changePasswordChallenge();
      final email = (res['email'] ?? '').toString();
      final phone = (res['phone'] ?? '').toString();
      setState(() {
        _resetMode = true;
        _busy = false;
        _sentTo = [
          if (email.isNotEmpty) 'email $email',
          if (phone.isNotEmpty) 'phone $phone',
        ].join(' and ');
      });
      if (note != null) _snack(note);
    } on ApiException catch (e) {
      setState(() {
        _error = e.message;
        _busy = false;
      });
    } catch (_) {
      setState(() {
        _error = 'Could not send a code';
        _busy = false;
      });
    }
  }

  Future<void> _verify() async {
    setState(() => _error = null);
    if (_otp.text.trim().isEmpty) {
      setState(() => _error = 'Enter the code we sent you');
      return;
    }
    if (!_validNew()) return;
    setState(() => _busy = true);
    try {
      await Services.i.auth.changePasswordVerify(_otp.text.trim(), _next.text);
      _done('Password updated');
    } on ApiException catch (e) {
      setState(() {
        _error = e.message;
        _busy = false;
      });
    } catch (_) {
      setState(() {
        _error = 'Invalid or expired code';
        _busy = false;
      });
    }
  }

  void _done(String msg) {
    if (!mounted) return;
    _snack(msg);
    Navigator.of(context).pop();
  }

  void _snack(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(_resetMode ? 'Reset password' : 'Change password')),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          if (_resetMode)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Text(
                'We sent a one-time code to your $_sentTo. Enter it below with your new password.',
                style: const TextStyle(color: Colors.black54, fontSize: 13),
              ),
            ),
          if (_resetMode)
            _field(_otp, 'One-time code', obscure: false, keyboard: TextInputType.number)
          else
            _field(_current, 'Current password', obscure: true),
          const SizedBox(height: 12),
          _field(_next, 'New password (min 8 characters)', obscure: true),
          const SizedBox(height: 12),
          _field(_confirm, 'Confirm new password', obscure: true),
          if (_error != null) ...[
            const SizedBox(height: 12),
            Text(_error!, style: const TextStyle(color: Colors.red)),
          ],
          const SizedBox(height: 20),
          FilledButton(
            onPressed: _busy ? null : (_resetMode ? _verify : _change),
            child: _busy
                ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
                : Text(_resetMode ? 'Reset password' : 'Update password'),
          ),
          const SizedBox(height: 8),
          TextButton(
            onPressed: _busy ? null : () => _startReset(),
            child: Text(_resetMode ? 'Resend code' : 'Forgot your current password?'),
          ),
        ],
      ),
    );
  }

  Widget _field(TextEditingController c, String label,
      {required bool obscure, TextInputType? keyboard}) {
    return TextField(
      controller: c,
      obscureText: obscure,
      keyboardType: keyboard,
      decoration: InputDecoration(labelText: label, border: const OutlineInputBorder()),
    );
  }
}
