import 'package:flutter/material.dart';

import '../services.dart';
import '../push/push_service.dart';
import '../auth/otp_login_screen.dart';
import 'projects_screen.dart';
import 'estimates_screen.dart';
import 'designs_screen.dart';
import 'payments_screen.dart';

/// The signed-in customer shell: four tabs over the Client BFF, one AppBar with
/// sign-out. Tabs are kept alive by IndexedStack so switching doesn't reload.
class HomeShell extends StatefulWidget {
  const HomeShell({super.key});

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _index = 0;

  static const _titles = ['My Project', 'Estimates', 'Designs', 'Payments'];
  final _tabs = const [ProjectsTab(), EstimatesTab(), DesignsTab(), PaymentsTab()];

  @override
  void initState() {
    super.initState();
    // Now that a customer is signed in, register this device for push (no-op
    // until Firebase is configured).
    PushService.instance.registerAfterLogin(Services.i.auth.registerDevice);
  }

  Future<void> _logout() async {
    await PushService.instance.onLogout(Services.i.auth.unregisterDevice); // before tokens are cleared
    await Services.i.auth.logout();
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const OtpLoginScreen()),
      (_) => false,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_titles[_index]),
        actions: [
          IconButton(icon: const Icon(Icons.logout), tooltip: 'Sign out', onPressed: _logout),
        ],
      ),
      body: IndexedStack(index: _index, children: _tabs),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.home_outlined), selectedIcon: Icon(Icons.home), label: 'Home'),
          NavigationDestination(icon: Icon(Icons.receipt_long_outlined), selectedIcon: Icon(Icons.receipt_long), label: 'Estimates'),
          NavigationDestination(icon: Icon(Icons.view_in_ar_outlined), selectedIcon: Icon(Icons.view_in_ar), label: 'Designs'),
          NavigationDestination(icon: Icon(Icons.payments_outlined), selectedIcon: Icon(Icons.payments), label: 'Payments'),
        ],
      ),
    );
  }
}
