import 'package:flutter/material.dart';

import 'src/services.dart';
import 'src/push/push_service.dart';
import 'src/auth/login_screen.dart';
import 'src/home/company_shell.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // No-op until Firebase is configured (see PUSH_SETUP.md).
  await PushService.instance.init(onOpen: (data) {
    // data['type'] deep-link routing hooks here.
  });
  runApp(const CompanyApp());
}

class CompanyApp extends StatelessWidget {
  const CompanyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Interio Junction — Team',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorSchemeSeed: const Color(0xFF5C3A21), // CRM brown
        useMaterial3: true,
      ),
      home: const _Root(),
    );
  }
}

class _Root extends StatelessWidget {
  const _Root();

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<bool>(
      future: Services.i.tokens.hasSession,
      builder: (context, snap) {
        if (!snap.hasData) {
          return const Scaffold(body: Center(child: CircularProgressIndicator()));
        }
        return snap.data! ? const CompanyShell() : const LoginScreen();
      },
    );
  }
}
