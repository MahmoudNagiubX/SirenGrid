import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:sirengrid_citizen/core/api_client.dart';
import 'package:sirengrid_citizen/core/location.dart';
import 'package:sirengrid_citizen/core/storage.dart';
import 'package:sirengrid_citizen/design/components/sg_cards.dart';
import 'package:sirengrid_citizen/design/theme.dart';
import 'package:sirengrid_citizen/features/auth/auth_cubit.dart';
import 'package:sirengrid_citizen/features/auth/login_screen.dart';
import 'package:sirengrid_citizen/features/emergency/emergency_service.dart';
import 'package:sirengrid_citizen/l10n/strings.dart';

import 'support.dart';

Widget _host(Widget child, {List<BlocProvider> providers = const []}) {
  final app = MaterialApp(
    theme: sgTheme(),
    supportedLocales: SgStrings.supportedLocales,
    home: child,
  );
  return providers.isEmpty
      ? app
      : MultiBlocProvider(providers: providers, child: app);
}

void main() {
  setUpAll(() => GoogleFonts.config.allowRuntimeFetching = false);
  setUp(() => SecureStore.useInMemory());
  tearDown(() => SecureStore.reset());

  testWidgets('Login screen renders phone + PIN + submit', (tester) async {
    final auth = AuthCubit(ApiClient(client: ScriptedClient()));
    await tester.pumpWidget(
      _host(
        const LoginScreen(),
        providers: [BlocProvider<AuthCubit>.value(value: auth)],
      ),
    );
    expect(find.byKey(const Key('login_screen')), findsOneWidget);
    expect(find.text('Phone number'), findsOneWidget);
    expect(find.text('PIN'), findsOneWidget);
    expect(find.text('Log in'), findsOneWidget);
    await auth.close();
  });

  testWidgets('Service card toggles selected visual on tap', (tester) async {
    var selected = false;
    await tester.pumpWidget(
      _host(
        StatefulBuilder(
          builder: (context, setState) => Scaffold(
            body: Center(
              child: SizedBox(
                width: 180,
                child: SgServiceCard(
                  icon: EmergencyService.ambulance.icon,
                  label: 'Ambulance',
                  selected: selected,
                  onTap: () => setState(() => selected = !selected),
                ),
              ),
            ),
          ),
        ),
      ),
    );
    expect(selected, isFalse);
    await tester.tap(find.text('Ambulance'));
    await tester.pump();
    expect(selected, isTrue);
  });

  testWidgets('every EmergencyService maps to a frozen backend code', (
    tester,
  ) async {
    expect(EmergencyService.values.map((s) => s.apiCode).toSet(), {
      'AMBULANCE',
      'FIRE',
      'POLICE',
      'GENERAL',
    });
  });

  testWidgets('LocationService.readiness maps a granted permission to ready', (
    tester,
  ) async {
    final svc = LocationService(FakeLocationPort());
    expect(await svc.readiness(), LocationReadiness.ready);
  });
}
