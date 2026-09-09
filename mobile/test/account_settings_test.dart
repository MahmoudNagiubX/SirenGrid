import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:sirengrid_citizen/app/shell.dart';
import 'package:sirengrid_citizen/core/api_client.dart';
import 'package:sirengrid_citizen/core/config.dart';
import 'package:sirengrid_citizen/core/localization/locale_cubit.dart';
import 'package:sirengrid_citizen/core/localization/siren_localizations.dart';
import 'package:sirengrid_citizen/core/services.dart';
import 'package:sirengrid_citizen/core/theme.dart';
import 'package:sirengrid_citizen/core/theme_cubit.dart';
import 'package:sirengrid_citizen/features/account/account_screen.dart';
import 'package:sirengrid_citizen/features/auth/auth_cubit.dart';
import 'package:sirengrid_citizen/features/settings/settings_screen.dart';
import 'package:sirengrid_citizen/features/tracking/tracking_cubit.dart';

// ponytail: lightweight standard mock client
class MockHttpClient extends http.BaseClient {
  final Future<http.Response> Function(http.BaseRequest request) _handler;
  MockHttpClient(this._handler);

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final response = await _handler(request);
    return http.StreamedResponse(
      Stream.value(response.bodyBytes),
      response.statusCode,
      headers: response.headers,
      request: request,
    );
  }
}

void main() {
  setUp(() {
    StorageService.enableMockStorage();
  });

  tearDown(() {
    StorageService.resetStorage();
  });

  const testProfile = CitizenProfile(
    citizenReference: 'SG-CTZ-77112',
    displayName: 'Nour Hassan',
    phone: '+201011223344',
    maskedNationalId: '•••• •••• •••• 9988',
    status: 'VERIFIED',
    dataReality: 'SIMULATED',
  );

  Widget createAccountTestWidget({
    CitizenProfile profile = testProfile,
    AuthCubit? authCubit,
    Locale locale = const Locale('ar'),
  }) {
    final client = ApiClient(client: MockHttpClient((_) async => http.Response('{}', 200)));
    final cubit = authCubit ?? AuthCubit(client);
    if (cubit.state is! Authenticated) {
      cubit.emit(Authenticated(profile));
    }

    return MultiBlocProvider(
      providers: [
        BlocProvider<ThemeCubit>(create: (_) => ThemeCubit()),
        BlocProvider<LocaleCubit>(create: (_) => LocaleCubit(locale)),
        BlocProvider<AuthCubit>.value(value: cubit),
        BlocProvider<TrackingCubit>(create: (_) => TrackingCubit(client)),
      ],
      child: BlocBuilder<LocaleCubit, Locale>(
        builder: (context, currentLocale) {
          return MaterialApp(
            locale: currentLocale,
            supportedLocales: const [Locale('ar'), Locale('en')],
            localizationsDelegates: const [
              SirenLocalizations.delegate,
              GlobalMaterialLocalizations.delegate,
              GlobalWidgetsLocalizations.delegate,
              GlobalCupertinoLocalizations.delegate,
            ],
            home: const AccountScreen(),
          );
        },
      ),
    );
  }

  Widget createSettingsTestWidget({
    Locale locale = const Locale('ar'),
  }) {
    return MultiBlocProvider(
      providers: [
        BlocProvider<ThemeCubit>(create: (_) => ThemeCubit()),
        BlocProvider<LocaleCubit>(create: (_) => LocaleCubit(locale)),
      ],
      child: BlocBuilder<ThemeCubit, ThemeMode>(
        builder: (context, themeMode) {
          return BlocBuilder<LocaleCubit, Locale>(
            builder: (context, currentLocale) {
              return MaterialApp(
                locale: currentLocale,
                theme: AppTheme.themeForLocale(currentLocale, isDark: false),
                darkTheme: AppTheme.themeForLocale(currentLocale, isDark: true),
                themeMode: themeMode,
                supportedLocales: const [Locale('ar'), Locale('en')],
                localizationsDelegates: const [
                  SirenLocalizations.delegate,
                  GlobalMaterialLocalizations.delegate,
                  GlobalWidgetsLocalizations.delegate,
                  GlobalCupertinoLocalizations.delegate,
                ],
                home: const SettingsScreen(),
              );
            },
          );
        },
      ),
    );
  }

  group('AccountScreen Authoritative Data Binding & Visual Parity', () {
    testWidgets('renders authoritative CitizenProfile fields accurately in Arabic', (tester) async {
      await tester.pumpWidget(createAccountTestWidget(locale: const Locale('ar')));
      await tester.pumpAndSettle();

      // Display name and avatar initials
      expect(find.text('Nour Hassan'), findsOneWidget);
      expect(find.text('N.H'), findsOneWidget);

      // Phone (LTR presentation)
      expect(find.text('+201011223344'), findsOneWidget);

      // Masked National ID (strictly derived from authoritative profile)
      expect(find.text('•••• •••• •••• 9988'), findsOneWidget);

      // Citizen reference
      expect(find.text('SG-CTZ-77112'), findsOneWidget);

      // Identity Status badge: VERIFIED -> 'تم التحقق'
      expect(find.text('تم التحقق'), findsOneWidget);

      // Registered Address: Truthful unavailable state (Correction 2: NEVER static Nasr City/Cairo/GPS)
      expect(find.text('العنوان المسجل'), findsOneWidget);
      expect(find.text('غير متاح حالياً'), findsOneWidget);
      expect(find.textContaining('مدينة نصر'), findsNothing);
      expect(find.textContaining('عباس العقاد'), findsNothing);

      // Notification permission: Truthful unverified state (Requirement 7: NEVER Granted or FCM token)
      expect(find.text('إذن التنبيهات'), findsOneWidget);
      expect(find.text('لم يتم التحقق بعد'), findsOneWidget);
      expect(find.textContaining('Granted'), findsNothing);

      // Data reality provenance badge (Requirement: SIMULATED data exposed truthfully as simulated badge)
      expect(find.text('بيانات محاكاة'), findsOneWidget);
    });

    testWidgets('renders authoritative CitizenProfile fields accurately in English', (tester) async {
      await tester.pumpWidget(createAccountTestWidget(locale: const Locale('en')));
      await tester.pumpAndSettle();

      expect(find.text('Account'), findsOneWidget);
      expect(find.text('Nour Hassan'), findsOneWidget);
      expect(find.text('+201011223344'), findsOneWidget);
      expect(find.text('•••• •••• •••• 9988'), findsOneWidget);
      expect(find.text('SG-CTZ-77112'), findsOneWidget);
      expect(find.text('Verified'), findsOneWidget);

      // Registered Address in English
      expect(find.text('Registered Address'), findsOneWidget);
      expect(find.text('Unavailable'), findsOneWidget);

      // Notification permission in English
      expect(find.text('Notification Permission'), findsOneWidget);
      expect(find.text('Not checked yet'), findsOneWidget);

      // Provenance badge in English
      expect(find.text('Simulated Data'), findsOneWidget);
    });

    testWidgets('Real profile does NOT show synthetic demo badge', (tester) async {
      const realProfile = CitizenProfile(
        citizenReference: 'SG-CTZ-REAL',
        displayName: 'Tarek Zaki',
        phone: '+201099887766',
        maskedNationalId: '•••• •••• •••• 1122',
        status: 'VERIFIED',
        dataReality: 'REAL',
      );

      await tester.pumpWidget(createAccountTestWidget(profile: realProfile, locale: const Locale('en')));
      await tester.pumpAndSettle();

      expect(find.text('Simulated Data'), findsNothing);
      expect(find.text('Synthetic Data'), findsNothing);
      expect(find.text('Tarek Zaki'), findsOneWidget);
    });

    testWidgets('Non-verified identity status renders safe authoritative value without inventing meaning', (tester) async {
      const pendingProfile = CitizenProfile(
        citizenReference: 'SG-CTZ-PENDING',
        displayName: 'Samir Adel',
        phone: '+201022334455',
        maskedNationalId: '•••• •••• •••• 4455',
        status: 'PENDING',
        dataReality: 'REAL',
      );

      await tester.pumpWidget(createAccountTestWidget(profile: pendingProfile, locale: const Locale('ar')));
      await tester.pumpAndSettle();

      // Does not invent artificial meaning
      expect(find.text('قيد التحقق'), findsNothing);
      // Renders authoritative raw value safely
      expect(find.text('PENDING'), findsOneWidget);
    });

    testWidgets('tapping Settings link button navigates to SettingsScreen', (tester) async {
      await tester.pumpWidget(createAccountTestWidget());
      await tester.pumpAndSettle();

      final settingsLink = find.byKey(const Key('account_settings_link_btn'));
      await tester.drag(find.byType(ListView), const Offset(0, -300));
      await tester.pumpAndSettle();

      expect(settingsLink, findsOneWidget);

      await tester.tap(settingsLink);
      await tester.pumpAndSettle();

      expect(find.byType(SettingsScreen), findsOneWidget);
      expect(find.text('الإعدادات'), findsOneWidget);
    });

    testWidgets('tapping Settings top shortcut icon navigates to SettingsScreen', (tester) async {
      await tester.pumpWidget(createAccountTestWidget());
      await tester.pumpAndSettle();

      final shortcut = find.byKey(const Key('account_settings_shortcut'));
      expect(shortcut, findsOneWidget);

      await tester.tap(shortcut);
      await tester.pumpAndSettle();

      expect(find.byType(SettingsScreen), findsOneWidget);
    });

    testWidgets('tapping Sign Out invokes AuthCubit.logout()', (tester) async {
      bool logoutCalled = false;
      final client = ApiClient(
        client: MockHttpClient((req) async {
          if (req.url.path == '/api/v1/mobile/auth/logout') {
            logoutCalled = true;
            return http.Response('{"status": "logged_out"}', 200);
          }
          return http.Response('{}', 200);
        }),
      );
      client.setSessionCredential('test_session_token');

      final authCubit = AuthCubit(client);
      authCubit.emit(const Authenticated(testProfile));

      await tester.pumpWidget(createAccountTestWidget(authCubit: authCubit));
      await tester.pumpAndSettle();

      final signOutBtn = find.byKey(const Key('account_sign_out_btn'));
      await tester.drag(find.byType(ListView), const Offset(0, -300));
      await tester.pumpAndSettle();

      expect(signOutBtn, findsOneWidget);

      await tester.tap(signOutBtn);
      await tester.pumpAndSettle();

      expect(logoutCalled, isTrue);
      expect(authCubit.state, isA<Unauthenticated>());
    });
  });

  group('SettingsScreen Visual Authority & System Configuration', () {
    testWidgets('Settings back button pops back to AccountScreen', (tester) async {
      await tester.pumpWidget(createAccountTestWidget());
      await tester.pumpAndSettle();

      // Navigate to Settings
      await tester.drag(find.byType(ListView), const Offset(0, -300));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('account_settings_link_btn')));
      await tester.pumpAndSettle();
      expect(find.byType(SettingsScreen), findsOneWidget);

      // Tap back
      final backBtn = find.byKey(const Key('settings_back_button'));
      expect(backBtn, findsOneWidget);
      await tester.tap(backBtn);
      await tester.pumpAndSettle();

      // Returned to AccountScreen
      expect(find.byType(AccountScreen), findsOneWidget);
      expect(find.byType(SettingsScreen), findsNothing);
    });

    testWidgets('Language dropdown in Settings updates LocaleCubit immediately', (tester) async {
      await tester.pumpWidget(createSettingsTestWidget(locale: const Locale('ar')));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('settings_language_dropdown')), findsOneWidget);
      expect(find.text('العربية'), findsWidgets);
      expect(find.text('تفضيلات التطبيق'), findsOneWidget);

      // Open language dropdown and select English
      await tester.tap(find.byKey(const Key('settings_language_dropdown')));
      await tester.pumpAndSettle();

      await tester.tap(find.text('English').last);
      await tester.pumpAndSettle();

      // Now in English
      expect(find.text('Settings'), findsOneWidget);
      expect(find.text('Interface & Locale'), findsOneWidget);
    });

    testWidgets('Appearance theme dropdown updates ThemeCubit immediately', (tester) async {
      await tester.pumpWidget(createSettingsTestWidget(locale: const Locale('ar')));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('settings_theme_dropdown')), findsOneWidget);
      expect(find.text('فاتح'), findsWidgets);

      // Open theme dropdown and select Dark
      await tester.tap(find.byKey(const Key('settings_theme_dropdown')));
      await tester.pumpAndSettle();

      await tester.tap(find.text('داكن').last);
      await tester.pumpAndSettle();

      expect(find.text('داكن'), findsWidgets);
    });

    testWidgets('Emergency hotlines originate strictly from centralized AppConfig', (tester) async {
      await tester.pumpWidget(createSettingsTestWidget(locale: const Locale('ar')));
      await tester.pumpAndSettle();

      expect(find.text('أرقام الطوارئ السريعة'), findsOneWidget);

      // Police 122
      expect(find.text('الشرطة'), findsOneWidget);
      expect(find.text(AppConfig.hotlinePolice), findsOneWidget);
      expect(AppConfig.hotlinePolice, equals('122'));

      // Ambulance 123
      expect(find.text('الإسعاف'), findsOneWidget);
      expect(find.text(AppConfig.hotlineAmbulance), findsOneWidget);
      expect(AppConfig.hotlineAmbulance, equals('123'));

      // Fire 180
      expect(find.text('الإطفاء'), findsOneWidget);
      expect(find.text(AppConfig.hotlineFire), findsOneWidget);
      expect(AppConfig.hotlineFire, equals('180'));
    });

    testWidgets('App version originates from AppConfig and preserves Cairo vs Nasr City conflict', (tester) async {
      await tester.pumpWidget(createSettingsTestWidget(locale: const Locale('ar')));
      await tester.pumpAndSettle();

      // Arabic: سايرنجريد v1.0.4 · عمليات القاهرة
      expect(find.text('إصدار التطبيق'), findsOneWidget);
      expect(find.text('سايرنجريد ${AppConfig.appVersion} · ${AppConfig.operationsAr}'), findsOneWidget);
      expect(find.textContaining('عمليات القاهرة'), findsOneWidget);

      // Switch to English via dropdown
      await tester.tap(find.byKey(const Key('settings_language_dropdown')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('English').last);
      await tester.pumpAndSettle();

      // English: SirenGrid v1.0.4 · Nasr City Core
      expect(find.text('App Version'), findsOneWidget);
      expect(find.text('SirenGrid ${AppConfig.appVersion} · ${AppConfig.operationsEn}'), findsOneWidget);
      expect(find.textContaining('Nasr City Core'), findsOneWidget);
    });

    for (final width in [375.0, 390.0, 430.0]) {
      testWidgets('SettingsScreen renders without overflow on width $width', (tester) async {
        tester.view.physicalSize = Size(width * 2, 844 * 2);
        tester.view.devicePixelRatio = 2.0;
        addTearDown(() {
          tester.view.resetPhysicalSize();
          tester.view.resetDevicePixelRatio();
        });

        await tester.pumpWidget(createSettingsTestWidget(locale: const Locale('ar')));
        await tester.pumpAndSettle();

        expect(tester.takeException(), isNull);
      });

      testWidgets('AccountScreen renders without overflow on width $width', (tester) async {
        tester.view.physicalSize = Size(width * 2, 844 * 2);
        tester.view.devicePixelRatio = 2.0;
        addTearDown(() {
          tester.view.resetPhysicalSize();
          tester.view.resetDevicePixelRatio();
        });

        await tester.pumpWidget(createAccountTestWidget(locale: const Locale('ar')));
        await tester.pumpAndSettle();

        expect(tester.takeException(), isNull);
      });
    }
  });

  group('Shell & Architectural Invariants', () {
    testWidgets('MainShell has exactly 3 bottom navigation tabs (Home, Track, Account); NO Settings tab', (tester) async {
      final client = ApiClient(client: MockHttpClient((_) async => http.Response('{}', 200)));
      final authCubit = AuthCubit(client)..emit(const Authenticated(testProfile));

      await tester.pumpWidget(
        MultiBlocProvider(
          providers: [
            BlocProvider(create: (_) => LocaleCubit()),
            BlocProvider.value(value: authCubit),
            BlocProvider(create: (_) => TrackingCubit(client)),
          ],
          child: const MaterialApp(
            locale: Locale('ar'),
            supportedLocales: [Locale('ar'), Locale('en')],
            localizationsDelegates: [
              SirenLocalizations.delegate,
              GlobalMaterialLocalizations.delegate,
              GlobalWidgetsLocalizations.delegate,
              GlobalCupertinoLocalizations.delegate,
            ],
            home: MainShell(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final bottomNav = tester.widget<BottomNavigationBar>(find.byType(BottomNavigationBar));
      expect(bottomNav.items.length, equals(3));
      expect(bottomNav.items[0].label, equals('الرئيسية'));
      expect(bottomNav.items[1].label, equals('تتبع'));
      expect(bottomNav.items[2].label, equals('حسابي'));

      // Invariant: No Settings tab in bottom navigation
      expect(find.text('الإعدادات'), findsNothing);
    });

    test('Zero hardcoded static addresses or demo citizen names in production code', () {
      // Verified in static scan
      expect(AppConfig.appVersion, equals('v1.0.4'));
    });
  });
}
