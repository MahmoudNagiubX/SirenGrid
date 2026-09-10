import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:sirengrid_citizen/core/api_client.dart';
import 'package:sirengrid_citizen/core/location.dart';
import 'package:sirengrid_citizen/core/storage.dart';
import 'package:sirengrid_citizen/design/theme.dart';
import 'package:sirengrid_citizen/features/auth/auth_cubit.dart';
import 'package:sirengrid_citizen/features/emergency/home_cubit.dart';
import 'package:sirengrid_citizen/features/emergency/home_screen.dart';
import 'package:sirengrid_citizen/features/emergency/location_cubit.dart';
import 'package:sirengrid_citizen/l10n/strings.dart';

import 'support.dart';

Widget _homeHost() {
  final api = ApiClient(client: ScriptedClient());
  final location = LocationService(FakeLocationPort());
  return MultiBlocProvider(
    providers: [
      BlocProvider(create: (_) => AuthCubit(api)),
      BlocProvider(create: (_) => LocationCubit(location)..refresh()),
      BlocProvider(create: (_) => HomeCubit(api, location)),
    ],
    child: MaterialApp(
      theme: sgTheme(),
      supportedLocales: SgStrings.supportedLocales,
      home: HomeScreen(onOpenAccount: () {}, onSubmitted: (_) {}),
    ),
  );
}

Future<void> _pumpAt(WidgetTester tester, Size size) async {
  // `TestWidgetsFlutterBinding.setSurfaceSize` only resizes the root render
  // view; it does not update `tester.view.physicalSize`, which is what
  // `MediaQuery.sizeOf` actually reads. That mismatch silently ran every test
  // below against the default 800x600 test window instead of the requested
  // size. Setting the view directly keeps both in sync.
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  await tester.pumpWidget(_homeHost());
  await tester.pump(const Duration(milliseconds: 350));
}

void main() {
  setUpAll(() => GoogleFonts.config.allowRuntimeFetching = false);
  setUp(() => SecureStore.useInMemory());
  tearDown(() => SecureStore.reset());

  testWidgets('Step 1 pill is gone', (tester) async {
    await _pumpAt(tester, const Size(393, 800));
    expect(find.text('Step 1'), findsNothing);
    expect(find.text('Which service do you need?'), findsOneWidget);
  });

  testWidgets('all four service cards + Request CTA fit with no scroll', (
    tester,
  ) async {
    await _pumpAt(tester, const Size(393, 800));
    expect(tester.takeException(), isNull);

    for (final name in ['ambulance', 'fire', 'police', 'general']) {
      expect(find.byKey(Key('service_card_$name')), findsOneWidget);
    }
    expect(find.textContaining('Request'), findsOneWidget);

    // No wrapping scroll container in the Home body at the target size — the
    // service grid's own inert `Scrollable` (shrink-wrapped,
    // NeverScrollableScrollPhysics) is a GridView implementation detail, not a
    // scrolling section, so it is deliberately not what this asserts against.
    expect(
      find.descendant(
        of: find.byKey(const Key('home_screen')),
        matching: find.byType(SingleChildScrollView),
      ),
      findsNothing,
    );
  });

  testWidgets('no overflow on a compact phone viewport', (tester) async {
    await _pumpAt(tester, const Size(360, 720));
    expect(tester.takeException(), isNull);
    for (final name in ['ambulance', 'fire', 'police', 'general']) {
      expect(find.byKey(Key('service_card_$name')), findsOneWidget);
    }
  });

  testWidgets('tall viewport keeps the CTA in the upper-middle, not floored', (
    tester,
  ) async {
    await _pumpAt(tester, const Size(412, 915));
    expect(tester.takeException(), isNull);

    final ctaTop = tester.getTopLeft(find.textContaining('Request')).dy;
    final lastRowBottom = tester
        .getBottomLeft(find.byKey(const Key('service_card_police')))
        .dy;
    // CTA sits a tight, bounded gap below the last card row — never dumped at
    // the very bottom of the screen.
    expect(ctaTop - lastRowBottom, greaterThan(8));
    expect(ctaTop - lastRowBottom, lessThan(140));
  });
}
