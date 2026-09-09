// On-device end-to-end smoke of the citizen flow against a REAL SirenGrid
// backend (run with `adb reverse tcp:8000 tcp:8000` + a seeded backend on the
// host, --dart-define=API_URL=http://localhost:8000).
//
//   flutter test integration_test/citizen_flow_test.dart -d <device> \
//     --dart-define=API_URL=http://localhost:8000
//
// Location runtime permission must be pre-granted:
//   adb -s <device> shell pm grant eg.sirengrid.sirengrid_citizen \
//     android.permission.ACCESS_FINE_LOCATION
//
// Login -> Home -> request Ambulance -> confirm -> Tracking -> Account -> logout.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:sirengrid_citizen/main.dart' as app;

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  Future<void> pumpUntil(
    WidgetTester tester,
    Finder finder, {
    Duration timeout = const Duration(seconds: 25),
  }) async {
    final deadline = DateTime.now().add(timeout);
    while (DateTime.now().isBefore(deadline)) {
      await tester.pump(const Duration(milliseconds: 250));
      if (finder.evaluate().isNotEmpty) return;
    }
    fail('Timed out waiting for a matching widget.');
  }

  testWidgets('citizen can log in, request an ambulance, track, and log out', (
    tester,
  ) async {
    await app.bootstrap();
    await tester.pump(const Duration(seconds: 2));

    // --- Login -------------------------------------------------------------
    await pumpUntil(
      tester,
      find.byKey(const Key('login_screen')),
      timeout: const Duration(seconds: 40),
    );
    final fields = find.byType(TextField);
    await tester.enterText(fields.at(0), '01000000000');
    await tester.enterText(fields.at(1), '1234');
    await tester.pump(const Duration(milliseconds: 200));
    await tester.tap(find.text('Log in'));

    // --- Emergency Home --------------------------------------------------
    await pumpUntil(
      tester,
      find.byKey(const Key('home_screen')),
      timeout: const Duration(seconds: 30),
    );
    expect(find.textContaining('Request'), findsWidgets);

    // Ambulance is selected by default -> open the confirmation sheet.
    await tester.tap(find.textContaining('Request Ambulance').first);
    await pumpUntil(tester, find.text('Confirm request'));
    await tester.tap(find.text('Confirm request'));

    // --- Live Response Tracking ---------------------------------------
    await pumpUntil(
      tester,
      find.byKey(const Key('tracking_screen')),
      timeout: const Duration(seconds: 40),
    );
    // Some backend-owned state is shown (status headline / chip).
    await tester.pump(const Duration(seconds: 3));

    // --- Account + logout -------------------------------------------
    await tester.tap(find.text('Account'));
    await pumpUntil(tester, find.byKey(const Key('account_screen')));
    expect(find.text('Demo Citizen'), findsOneWidget);
    await tester.tap(find.text('Sign out'));

    await pumpUntil(
      tester,
      find.byKey(const Key('login_screen')),
      timeout: const Duration(seconds: 15),
    );
  });
}
