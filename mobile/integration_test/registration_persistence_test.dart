// On-device end-to-end smoke of citizen self-registration and its backend
// persistence, against a REAL SirenGrid backend (run with
// `adb reverse tcp:8000 tcp:8000` + a running backend on the host,
// --dart-define=API_URL=http://localhost:8000).
//
//   flutter test integration_test/registration_persistence_test.dart \
//     -d <device> --dart-define=API_URL=http://localhost:8000
//
// Uses a synthetic, timestamp-derived phone/National ID so the test can be
// re-run against a persistent backend DB without a duplicate-account
// conflict. National ID is 14 synthetic digits; only its last-4 and a
// one-way fingerprint are ever persisted server-side (see PD-081 / the
// mobile_auth module docstring) — never the full number.
//
// Login -> Create Account -> Home (authenticated) -> Account shows the
// persisted profile -> logout -> log back in with the same phone+PIN ->
// Account again shows the same profile (proves the round trip through the
// backend's SQLite-backed CitizenProfile, not just in-memory cubit state).

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
    fail('Timed out waiting for a matching widget: $finder');
  }

  testWidgets(
    'citizen can self-register, and the account survives logout/login',
    (tester) async {
      // Unique per run so repeat runs against a persistent backend DB never
      // collide with a prior run's phone/National ID.
      final suffix = DateTime.now().millisecondsSinceEpoch
          .toString()
          .substring(3);
      final phone = '01${suffix.padLeft(9, '0').substring(0, 9)}';
      final nationalId = suffix.padLeft(14, '1');
      const name = 'Automated QA Citizen';
      const pin = '4321';
      const address = 'Test Address, Nasr City';

      await app.bootstrap();
      await tester.pump(const Duration(seconds: 2));

      // --- Login screen -> Create account -----------------------------
      await pumpUntil(
        tester,
        find.byKey(const Key('login_screen')),
        timeout: const Duration(seconds: 40),
      );
      await tester.tap(find.text('Create account'));
      await pumpUntil(tester, find.byKey(const Key('register_screen')));

      // --- Fill registration form --------------------------------------
      final fields = find.byType(TextField);
      expect(fields, findsNWidgets(6));
      await tester.enterText(fields.at(0), name);
      await tester.enterText(fields.at(1), phone);
      await tester.enterText(fields.at(2), nationalId);
      await tester.enterText(fields.at(3), pin);
      await tester.enterText(fields.at(4), pin);
      await tester.enterText(fields.at(5), address);
      await tester.pump(const Duration(milliseconds: 200));
      await tester.tap(find.byKey(const Key('register_submit')));

      // --- Registration succeeds straight to Home -----------------------
      await pumpUntil(
        tester,
        find.byKey(const Key('home_screen')),
        timeout: const Duration(seconds: 30),
      );
      expect(find.text('Good day, $name'), findsOneWidget);

      // --- Account shows the persisted profile ---------------------------
      await tester.tap(find.text('Account'));
      await pumpUntil(tester, find.byKey(const Key('account_screen')));
      // The profile loads asynchronously after the scaffold itself appears.
      await pumpUntil(tester, find.text(name));
      expect(find.text(address), findsOneWidget);
      // Full National ID must never reach the client; only masked digits do.
      expect(find.textContaining(nationalId), findsNothing);

      // --- Logout ---------------------------------------------------------
      // Account's ListView only mounts elements near the viewport (true of
      // any Sliver-backed list, not just `.builder`), so the sign-out control
      // below the fold genuinely does not exist for `find.text` until the
      // list is scrolled down to it. Other tabs stay mounted in the shell's
      // IndexedStack, so this must be scoped to account_screen specifically
      // rather than ".first" in tree order.
      await tester.scrollUntilVisible(
        find.text('Sign out'),
        200,
        scrollable: find.descendant(
          of: find.byKey(const Key('account_screen')),
          matching: find.byType(Scrollable),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Sign out'));
      await pumpUntil(
        tester,
        find.byKey(const Key('login_screen')),
        timeout: const Duration(seconds: 15),
      );

      // --- Log back in with the same phone + PIN --------------------------
      final loginFields = find.byType(TextField);
      await tester.enterText(loginFields.at(0), phone);
      await tester.enterText(loginFields.at(1), pin);
      await tester.pump(const Duration(milliseconds: 200));
      await tester.tap(find.text('Log in'));
      await pumpUntil(
        tester,
        find.byKey(const Key('home_screen')),
        timeout: const Duration(seconds: 30),
      );
      expect(find.text('Good day, $name'), findsOneWidget);

      // --- Account again shows the SAME persisted profile ------------------
      // (round-tripped from the backend, not held over in memory: this is a
      // fresh AuthCubit/session after a real logout.)
      await tester.tap(find.text('Account'));
      await pumpUntil(tester, find.byKey(const Key('account_screen')));
      await pumpUntil(tester, find.text(name));
      expect(find.text(phone), findsOneWidget);
      expect(find.text(address), findsOneWidget);
    },
  );
}
