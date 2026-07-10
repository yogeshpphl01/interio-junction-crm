import 'package:flutter/material.dart';

import '../services.dart';
import '../push/push_service.dart';
import '../auth/login_screen.dart';
import 'worklist_screen.dart';
import 'projects_screen.dart';

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

  @override
  void initState() {
    super.initState();
    PushService.instance.registerAfterLogin(Services.i.auth.registerDevice);
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
        actions: [IconButton(icon: const Icon(Icons.logout), tooltip: 'Sign out', onPressed: _logout)],
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
