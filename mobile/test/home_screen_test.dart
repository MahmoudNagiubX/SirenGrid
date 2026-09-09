import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator/geolocator.dart';
import 'package:sirengrid_citizen/app/shell.dart';
import 'package:sirengrid_citizen/core/api_client.dart';
import 'package:sirengrid_citizen/core/config.dart';
import 'package:sirengrid_citizen/core/localization/locale_cubit.dart';
import 'package:sirengrid_citizen/core/localization/siren_localizations.dart';
import 'package:sirengrid_citizen/core/services.dart';
import 'package:sirengrid_citizen/core/theme.dart';
import 'package:sirengrid_citizen/features/auth/auth_cubit.dart';
import 'package:sirengrid_citizen/features/emergency_home/emergency_service.dart';
import 'package:sirengrid_citizen/features/emergency_home/home_cubit.dart';
import 'package:sirengrid_citizen/features/emergency_home/home_screen.dart';
import 'package:sirengrid_citizen/features/emergency_home/widgets/confirmation_sheet.dart';
import 'package:sirengrid_citizen/features/emergency_home/widgets/emergency_service_card.dart';
import 'package:sirengrid_citizen/features/tracking/tracking_cubit.dart';

Widget createShellTestApp({
  required AuthCubit authCubit,
  LocaleCubit? localeCubit,
  ApiClient? apiClient,
}) {
  final client = apiClient ?? ApiClient();
  return MultiBlocProvider(
    providers: [
      BlocProvider<LocaleCubit>(create: (_) => localeCubit ?? LocaleCubit(const Locale('ar'))),
      BlocProvider<AuthCubit>.value(value: authCubit),
      BlocProvider<HomeCubit>(create: (_) => HomeCubit(client)),
      BlocProvider<TrackingCubit>(create: (_) => TrackingCubit(client)),
    ],
    child: BlocBuilder<LocaleCubit, Locale>(
      builder: (context, locale) {
        return MaterialApp(
          theme: AppTheme.themeForLocale(locale),
          locale: locale,
          supportedLocales: const [Locale('ar'), Locale('en')],
          localizationsDelegates: const [
            SirenLocalizations.delegate,
            GlobalMaterialLocalizations.delegate,
            GlobalWidgetsLocalizations.delegate,
            GlobalCupertinoLocalizations.delegate,
          ],
          home: const MainShell(enableSubmissionFlow: false),
        );
      },
    ),
  );
}

void main() {
  setUp(() {
    StorageService.enableMockStorage();
    LocationService.enableMockLocation(
      serviceEnabled: true,
      permission: LocationPermission.whileInUse,
      position: Position(
        latitude: 30.0561,
        longitude: 31.3452,
        timestamp: DateTime.now(),
        accuracy: 12.0,
        altitude: 0.0,
        altitudeAccuracy: 0.0,
        heading: 0.0,
        headingAccuracy: 0.0,
        speed: 0.0,
        speedAccuracy: 0.0,
      ),
    );
  });

  tearDown(() {
    StorageService.resetStorage();
    LocationService.resetMockLocation();
  });

  const testProfile = CitizenProfile(
    citizenReference: 'cit-test-01',
    displayName: 'Hassan Mahmoud',
    phone: '+201012345678',
    maskedNationalId: '•••• •••• •••• 1234',
    status: 'Verified',
    dataReality: 'DEMO',
  );

  group('MainShell Canonical Navigation', () {
    testWidgets('authenticated shell has exactly 3 tabs (Home, Track, Account)', (tester) async {
      final authCubit = AuthCubit(ApiClient());
      authCubit.emit(const Authenticated(testProfile));

      await tester.pumpWidget(createShellTestApp(authCubit: authCubit));
      await tester.pumpAndSettle();

      final navBar = tester.widget<BottomNavigationBar>(find.byType(BottomNavigationBar));
      expect(navBar.items.length, equals(3));
      expect(navBar.items[0].label, equals('الرئيسية'));
      expect(navBar.items[1].label, equals('تتبع'));
      expect(navBar.items[2].label, equals('حسابي'));
    });

    testWidgets('no Settings tab exists in bottom navigation', (tester) async {
      final authCubit = AuthCubit(ApiClient());
      authCubit.emit(const Authenticated(testProfile));

      await tester.pumpWidget(createShellTestApp(authCubit: authCubit));
      await tester.pumpAndSettle();

      expect(find.text('Settings'), findsNothing);
      expect(find.text('الإعدادات'), findsNothing);
      expect(find.byIcon(Icons.settings), findsNothing);
      expect(find.byIcon(Icons.settings_outlined), findsNothing);
    });
  });

  group('Emergency Home Visual Structure & User Data', () {
    testWidgets('Home renders citizen greeting from authenticated CitizenProfile', (tester) async {
      final authCubit = AuthCubit(ApiClient());
      authCubit.emit(const Authenticated(testProfile));

      await tester.pumpWidget(createShellTestApp(authCubit: authCubit));
      await tester.pumpAndSettle();

      // Greeting with authenticated display name
      expect(find.textContaining('Hassan Mahmoud'), findsOneWidget);
      // Initials badge
      expect(find.text('H.M'), findsOneWidget);
      // Reassuring subtitle
      expect(find.text('ابقَ آمناً — المساعدة على بعد لمسة واحدة'), findsOneWidget);
    });

    testWidgets('Home renders all four emergency services in 2x2 grid', (tester) async {
      final authCubit = AuthCubit(ApiClient());
      authCubit.emit(const Authenticated(testProfile));

      await tester.pumpWidget(createShellTestApp(authCubit: authCubit));
      await tester.pumpAndSettle();

      // Four service cards
      expect(find.byType(EmergencyServiceCard), findsNWidgets(4));
      expect(find.byKey(const Key('service_card_ambulance')), findsOneWidget);
      expect(find.byKey(const Key('service_card_fire')), findsOneWidget);
      expect(find.byKey(const Key('service_card_police')), findsOneWidget);
      expect(find.byKey(const Key('service_card_general')), findsOneWidget);

      // Service titles in Arabic
      expect(find.text('إسعاف'), findsOneWidget);
      expect(find.text('إطفاء'), findsOneWidget);
      expect(find.text('شرطة'), findsOneWidget);
      expect(find.text('طوارئ عامة'), findsOneWidget);
    });

    testWidgets('EmergencyServiceCard renders centered layout matching design reference', (tester) async {
      final authCubit = AuthCubit(ApiClient());
      authCubit.emit(const Authenticated(testProfile));

      await tester.pumpWidget(createShellTestApp(authCubit: authCubit));
      await tester.pumpAndSettle();

      final firstCardFinder = find.byType(EmergencyServiceCard).first;
      final columnFinder = find.descendant(of: firstCardFinder, matching: find.byType(Column));
      final Column column = tester.widget(columnFinder);
      expect(column.crossAxisAlignment, equals(CrossAxisAlignment.center));

      final titleFinder = find.descendant(of: firstCardFinder, matching: find.text('إسعاف'));
      final Text titleText = tester.widget(titleFinder);
      expect(titleText.textAlign, equals(TextAlign.center));
    });

    testWidgets('Hotline banner uses centralized AppConfig.hotlinePolice (122)', (tester) async {
      final authCubit = AuthCubit(ApiClient());
      authCubit.emit(const Authenticated(testProfile));

      await tester.pumpWidget(createShellTestApp(authCubit: authCubit));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('home_hotline_banner')), findsOneWidget);
      expect(find.textContaining(AppConfig.hotlinePolice), findsOneWidget);
      expect(find.text('122'), findsNothing); // Must not be bare standalone string, embedded in config string
      expect(find.textContaining('خطر وشيك؟ اتصل بـ 122'), findsOneWidget);
    });

    testWidgets('Location readiness card presents truthful readiness state without fake GPS claim', (tester) async {
      final authCubit = AuthCubit(ApiClient());
      authCubit.emit(const Authenticated(testProfile));

      await tester.pumpWidget(createShellTestApp(authCubit: authCubit));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('home_location_readiness_card')), findsOneWidget);
      // Must NOT claim fake Nasr City coordinates in Phase 4
      expect(find.textContaining('30.0561'), findsNothing);
      expect(find.textContaining('Nasr City, Cairo • GPS High Precision'), findsNothing);
    });
  });

  group('Bilingual Directionality & Layout', () {
    testWidgets('Arabic Home uses RTL directionality', (tester) async {
      final authCubit = AuthCubit(ApiClient());
      authCubit.emit(const Authenticated(testProfile));
      final localeCubit = LocaleCubit()..setLocale(const Locale('ar'));

      await tester.pumpWidget(createShellTestApp(authCubit: authCubit, localeCubit: localeCubit));
      await tester.pumpAndSettle();

      final textDirection = Directionality.of(tester.element(find.byType(HomeScreen)));
      expect(textDirection, equals(TextDirection.rtl));
      expect(find.text('طلب المساعدة الطارئة'), findsOneWidget);
    });

    testWidgets('English Home uses LTR directionality and English service labels', (tester) async {
      final authCubit = AuthCubit(ApiClient());
      authCubit.emit(const Authenticated(testProfile));
      final localeCubit = LocaleCubit()..setLocale(const Locale('en'));

      await tester.pumpWidget(createShellTestApp(authCubit: authCubit, localeCubit: localeCubit));
      await tester.pumpAndSettle();

      final textDirection = Directionality.of(tester.element(find.byType(HomeScreen)));
      expect(textDirection, equals(TextDirection.ltr));
      expect(find.text('Request Emergency Help'), findsOneWidget);
      expect(find.text('Ambulance'), findsOneWidget);
      expect(find.text('Fire'), findsOneWidget);
      expect(find.text('Police'), findsOneWidget);
      expect(find.text('General'), findsOneWidget);
    });
  });

  group('Confirmation Sheet Flow & Isolation', () {
    testWidgets('tapping Ambulance opens ConfirmationSheet with Ambulance metadata', (tester) async {
      final authCubit = AuthCubit(ApiClient());
      authCubit.emit(const Authenticated(testProfile));

      await tester.pumpWidget(createShellTestApp(authCubit: authCubit));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('service_card_ambulance')));
      await tester.pumpAndSettle();

      expect(find.byType(ConfirmationSheet), findsOneWidget);
      final sheet = tester.widget<ConfirmationSheet>(find.byType(ConfirmationSheet));
      expect(sheet.service.id, equals('ambulance'));
      expect(find.text('تأكيد — طلب إسعاف'), findsOneWidget);
    });

    testWidgets('tapping Fire opens ConfirmationSheet with Fire metadata', (tester) async {
      final authCubit = AuthCubit(ApiClient());
      authCubit.emit(const Authenticated(testProfile));

      await tester.pumpWidget(createShellTestApp(authCubit: authCubit));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('service_card_fire')));
      await tester.pumpAndSettle();

      expect(find.byType(ConfirmationSheet), findsOneWidget);
      final sheet = tester.widget<ConfirmationSheet>(find.byType(ConfirmationSheet));
      expect(sheet.service.id, equals('fire'));
      expect(find.text('تأكيد — طلب إطفاء'), findsOneWidget);
    });

    testWidgets('Cancel button dismisses ConfirmationSheet without side effects', (tester) async {
      final authCubit = AuthCubit(ApiClient());
      authCubit.emit(const Authenticated(testProfile));

      await tester.pumpWidget(createShellTestApp(authCubit: authCubit));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('service_card_police')));
      await tester.pumpAndSettle();

      expect(find.byType(ConfirmationSheet), findsOneWidget);

      await tester.tap(find.byKey(const Key('confirm_sheet_cancel_button')));
      await tester.pumpAndSettle();

      expect(find.byType(ConfirmationSheet), findsNothing);
    });

    testWidgets('Confirm button in Phase 4 closes sheet and does NOT fabricate requests or navigate to tracking', (tester) async {
      final authCubit = AuthCubit(ApiClient());
      authCubit.emit(const Authenticated(testProfile));

      await tester.pumpWidget(createShellTestApp(authCubit: authCubit));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('service_card_ambulance')));
      await tester.pumpAndSettle();

      // Tap Confirm
      await tester.tap(find.byKey(const Key('confirm_sheet_submit_button')));
      await tester.pumpAndSettle();

      // Sheet is closed
      expect(find.byType(ConfirmationSheet), findsNothing);

      // App remains on Home (does NOT navigate to Tracking)
      expect(find.byType(HomeScreen), findsOneWidget);

      // No active emergency request was saved to storage
      expect(await StorageService.getActiveRequestId(), isNull);
    });
  });

  group('Responsive Viewport Verification', () {
    for (final width in [375.0, 390.0, 430.0]) {
      testWidgets('HomeScreen renders without overflow at logical width $width', (tester) async {
        tester.view.physicalSize = Size(width * 3.0, 812.0 * 3.0);
        tester.view.devicePixelRatio = 3.0;

        final authCubit = AuthCubit(ApiClient());
        authCubit.emit(const Authenticated(testProfile));

        await tester.pumpWidget(createShellTestApp(authCubit: authCubit));
        await tester.pumpAndSettle();

        expect(tester.takeException(), isNull);
        expect(find.byType(HomeScreen), findsOneWidget);

        // Reset physical size
        addTearDown(() {
          tester.view.resetPhysicalSize();
          tester.view.resetDevicePixelRatio();
        });
      });
    }
  });

  group('Canonical 2x2 Emergency Service Icons Verification', () {
    test('Authoritative EmergencyService icon mappings conform to canonical design', () {
      final ambulance = EmergencyService.findById('ambulance');
      final fire = EmergencyService.findById('fire');
      final police = EmergencyService.findById('police');
      final general = EmergencyService.findById('general');

      // 1. Ambulance: Simple medical cross/plus icon, canonical SVG from stitch
      expect(ambulance.svgPath, isNotNull);
      expect(ambulance.svgPath, contains('M19 10.5h-5.5V5'));

      // 2. Fire: Stylized circular fire icon with canonical SVG path from stitch
      expect(fire.svgPath, isNotNull);
      expect(fire.svgPath, contains('M12 23c-4.97'));

      // 3. Police: Clean simple shield outline canonical SVG from stitch
      expect(police.svgPath, isNotNull);
      expect(police.svgPath, contains('M12 1L3 5v6'));

      // 4. General: Warning triangle canonical SVG from stitch
      expect(general.svgPath, isNotNull);
      expect(general.svgPath, contains('M1 21h22L12 2'));
    });

    testWidgets('Home cards render canonical icons with authoritative semantic styling', (tester) async {
      final authCubit = AuthCubit(ApiClient());
      authCubit.emit(const Authenticated(testProfile));

      await tester.pumpWidget(createShellTestApp(authCubit: authCubit));
      await tester.pumpAndSettle();

      // All four cards render CanonicalVectorIcon matching Stitch prototype
      expect(find.byType(CanonicalVectorIcon), findsNWidgets(4));
      expect(find.byKey(const Key('service_icon_ambulance')), findsOneWidget);
      expect(find.byKey(const Key('service_icon_fire')), findsOneWidget);
      expect(find.byKey(const Key('service_icon_police')), findsOneWidget);
      expect(find.byKey(const Key('service_icon_general')), findsOneWidget);
    });

    testWidgets('Same canonical icons render in English mode', (tester) async {
      final authCubit = AuthCubit(ApiClient());
      authCubit.emit(const Authenticated(testProfile));
      final localeCubit = LocaleCubit()..setLocale(const Locale('en'));

      await tester.pumpWidget(createShellTestApp(authCubit: authCubit, localeCubit: localeCubit));
      await tester.pumpAndSettle();

      expect(find.byType(CanonicalVectorIcon), findsNWidgets(4));
    });

    testWidgets('ConfirmationSheet renders canonical service icon', (tester) async {
      final authCubit = AuthCubit(ApiClient());
      authCubit.emit(const Authenticated(testProfile));

      await tester.pumpWidget(createShellTestApp(authCubit: authCubit));
      await tester.pumpAndSettle();

      // Open Fire sheet
      await tester.tap(find.byKey(const Key('service_card_fire')));
      await tester.pumpAndSettle();

      expect(find.byType(ConfirmationSheet), findsOneWidget);
      // Canonical stylized fire icon in sheet
      expect(find.descendant(of: find.byType(ConfirmationSheet), matching: find.byType(CanonicalVectorIcon)), findsOneWidget);

      await tester.tap(find.byKey(const Key('confirm_sheet_cancel_button')));
      await tester.pumpAndSettle();

      // Open Ambulance sheet
      await tester.tap(find.byKey(const Key('service_card_ambulance')));
      await tester.pumpAndSettle();

      expect(find.descendant(of: find.byType(ConfirmationSheet), matching: find.byType(CanonicalVectorIcon)), findsOneWidget);
    });
  });
}
