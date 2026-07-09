import 'package:flutter/material.dart';

import 'src/services.dart';
import 'src/auth/otp_login_screen.dart';
import 'src/home/projects_screen.dart';

void main() => runApp(const ClientApp());

class ClientApp extends StatelessWidget {
  const ClientApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Interio Junction',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorSchemeSeed: const Color(0xFF7C9082), // Booking green from the CRM palette
        useMaterial3: true,
      ),
      home: const _Root(),
    );
  }
}

/// Decide the first screen from whether a customer session already exists.
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
        return snap.data! ? const ProjectsScreen() : const OtpLoginScreen();
      },
    );
  }
}
