// Unit + widget tests for the customer app's shared UI helpers.
// These run with `flutter test` and need no backend, device or credentials.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:client_app/src/widgets.dart';

void main() {
  group('inr() — Indian rupee grouping', () {
    test('null shows a dash', () => expect(inr(null), '—'));
    test('hundreds are not grouped', () => expect(inr(500), '₹500'));
    test('thousands group at three', () => expect(inr(1000), '₹1,000'));
    test('lakhs group two-two-three', () => expect(inr(590000), '₹5,90,000'));
    test('a full contract value', () => expect(inr(850000), '₹8,50,000'));
    test('crores keep the grouping', () => expect(inr(12345678), '₹1,23,45,678'));
    test('negatives keep the sign after the symbol', () => expect(inr(-1000), '₹-1,000'));
    test('fractions are rounded', () => expect(inr(999.6), '₹1,000'));
  });

  testWidgets('StatusChip shows its label', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(home: Scaffold(body: StatusChip('accepted'))),
    );
    expect(find.text('accepted'), findsOneWidget);
  });

  testWidgets('EmptyState shows its icon and message', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(body: EmptyState(icon: Icons.inbox_outlined, text: 'No estimates yet')),
      ),
    );
    expect(find.text('No estimates yet'), findsOneWidget);
    expect(find.byIcon(Icons.inbox_outlined), findsOneWidget);
  });

  testWidgets('AsyncRefresh shows a spinner, then the loaded data', (tester) async {
    final completer = Completer<String>();
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: AsyncRefresh<String>(
            load: () => completer.future,
            onData: (data, refresh) => ListView(children: [Text(data)]),
          ),
        ),
      ),
    );

    expect(find.byType(CircularProgressIndicator), findsOneWidget);

    completer.complete('Estimate v2');
    await tester.pumpAndSettle();

    expect(find.byType(CircularProgressIndicator), findsNothing);
    expect(find.text('Estimate v2'), findsOneWidget);
  });

  testWidgets('AsyncRefresh offers Retry when loading fails', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: AsyncRefresh<String>(
            load: () async => throw Exception('network down'),
            onData: (data, refresh) => const SizedBox.shrink(),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Retry'), findsOneWidget);
  });
}
