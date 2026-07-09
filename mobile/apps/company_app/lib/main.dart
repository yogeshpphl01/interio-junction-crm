import 'package:flutter/material.dart';

import 'src/services.dart';
import 'src/auth/login_screen.dart';
import 'src/home/worklist_screen.dart';

void main() => runApp(const CompanyApp());

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
        return snap.data! ? const WorklistScreen() : const LoginScreen();
      },
    );
  }
}
