import 'package:flutter/material.dart';

import '../services.dart';
import '../push/push_service.dart';
import '../auth/login_screen.dart';
import '../auth/mfa_screens.dart';
import '../auth/change_password_screen.dart';
import 'worklist_screen.dart';
import 'projects_screen.dart';
import 'privacy_queue_screen.dart';

/// The signed-in employee shell: Work (role-aware worklist) + Projects
/// (production / site-ops). One AppBar with sign-out; push registration happens
/// here now that the employee is authenticated.
class CompanyShell extends StatefulWidget {
  const CompanyShell({super.key});

  @override
  State<CompanyShell> createState() => _CompanyShellState();
}

class _CompanyShellState extends State<CompanyShell> {
  int _index = 0;
  static const _titles = ['My Work', 'Projects'];
  final _tabs = const [WorklistTab(), ProjectsTab()];

  // Only admins (users.manage) see the DPDP erasure queue on this device.
  bool _canManagePrivacy = false;

  @override
  void initState() {
    super.initState();
    PushService.instance.registerAfterLogin(Services.i.auth.registerDevice);
    _loadPermissions();
  }

  Future<void> _loadPermissions() async {
    try {
      final me = await Services.i.data.me();
      final perms = ((me['permissions'] as List?) ?? const []).cast<String>();
      if (mounted) setState(() => _canManagePrivacy = perms.contains('users.manage'));
    } catch (_) {
      // Non-fatal: without the flag we simply hide the privacy queue.
    }
  }

  Future<void> _logout() async {
    await PushService.instance.onLogout(Services.i.auth.unregisterDevice); // before tokens cleared
    await Services.i.auth.logout();
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const LoginScreen()),
      (_) => false,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_titles[_index]),
        actions: [
          if (_canManagePrivacy)
            IconButton(
              icon: const Icon(Icons.shield_outlined),
              tooltip: 'Data erasure requests',
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const PrivacyQueueScreen())),
            ),
          IconButton(
            icon: const Icon(Icons.key_outlined),
            tooltip: 'Change password',
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => const ChangePasswordScreen())),
          ),
          IconButton(
            icon: const Icon(Icons.security),
            tooltip: 'Two-factor auth',
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => const MfaEnrollScreen())),
          ),
          IconButton(icon: const Icon(Icons.logout), tooltip: 'Sign out', onPressed: _logout),
        ],
      ),
      body: IndexedStack(index: _index, children: _tabs),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.checklist_outlined), selectedIcon: Icon(Icons.checklist), label: 'Work'),
          NavigationDestination(icon: Icon(Icons.factory_outlined), selectedIcon: Icon(Icons.factory), label: 'Projects'),
        ],
      ),
    );
  }
}
