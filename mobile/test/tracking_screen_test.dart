import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:sirengrid_citizen/core/api_client.dart';
import 'package:sirengrid_citizen/design/theme.dart';
import 'package:sirengrid_citizen/features/tracking/tracking_cubit.dart';
import 'package:sirengrid_citizen/features/tracking/tracking_screen.dart';
import 'package:sirengrid_citizen/l10n/strings.dart';

import 'support.dart';

/// Reproduces the real-device regression: TrackingScreen's dispose() used to
/// call `context.read<TrackingCubit>()`, which throws "Looking up a
/// deactivated widget's ancestor is unsafe" when the screen and its
/// BlocProvider ancestor are torn down together in the same frame (e.g. a
/// logout-style route replacement) — not just when the screen alone is
/// popped with the provider still above it.
void main() {
  setUpAll(() => GoogleFonts.config.allowRuntimeFetching = false);

  testWidgets(
    'disposing TrackingScreen together with its BlocProvider ancestor throws nothing',
    (tester) async {
      final cubit = TrackingCubit(ApiClient(client: ScriptedClient()));

      await tester.pumpWidget(
        MaterialApp(
          theme: sgTheme(),
          supportedLocales: SgStrings.supportedLocales,
          home: Navigator(
            onGenerateRoute: (settings) => MaterialPageRoute<void>(
              builder: (_) => BlocProvider<TrackingCubit>.value(
                value: cubit,
                child: TrackingScreen(onGoHome: () {}),
              ),
            ),
          ),
        ),
      );
      await tester.pump(const Duration(milliseconds: 50));
      expect(find.byKey(const Key('tracking_screen')), findsOneWidget);

      // Replace the whole route (screen + its BlocProvider ancestor) in one
      // transaction, exactly like the shell swapping MainShell for
      // LoginScreen on logout — this is what exposed the crash.
      await tester.pumpWidget(
        MaterialApp(
          theme: sgTheme(),
          supportedLocales: SgStrings.supportedLocales,
          home: const Scaffold(body: Center(child: Text('login_screen'))),
        ),
      );
      await tester.pump(const Duration(milliseconds: 50));

      expect(tester.takeException(), isNull);
      await cubit.close();
    },
  );
}
