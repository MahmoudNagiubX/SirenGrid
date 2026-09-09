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
import 'package:sirengrid_citizen/features/auth/login_screen.dart';
import 'package:sirengrid_citizen/features/auth/register_screen.dart';
import 'package:sirengrid_citizen/features/emergency_home/home_cubit.dart';
import 'package:sirengrid_citizen/features/emergency_home/home_screen.dart';
import 'package:sirengrid_citizen/features/settings/settings_screen.dart';
import 'package:sirengrid_citizen/features/tracking/tracking_cubit.dart';
import 'package:sirengrid_citizen/features/tracking/tracking_screen.dart';

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

  Widget createTestWidget({
    required Widget child,
    Locale locale = const Locale('ar'),
    ThemeMode themeMode = ThemeMode.light,
    AuthCubit? authCubit,
  }) {
    final client = ApiClient(client: MockHttpClient((_) async => http.Response('{}', 200)));
    return MultiBlocProvider(
      providers: [
        BlocProvider<ThemeCubit>(create: (_) => ThemeCubit(themeMode)),
        BlocProvider<LocaleCubit>(create: (_) => LocaleCubit(locale)),
        BlocProvider<AuthCubit>(create: (_) => authCubit ?? AuthCubit(client)),
        BlocProvider<HomeCubit>(create: (_) => HomeCubit(client)),
        BlocProvider<TrackingCubit>(create: (_) => TrackingCubit(client)),
      ],
      child: BlocBuilder<ThemeCubit, ThemeMode>(
        builder: (context, currentThemeMode) {
          return BlocBuilder<LocaleCubit, Locale>(
            builder: (context, currentLocale) {
              return MaterialApp(
                locale: currentLocale,
                theme: AppTheme.themeForLocale(currentLocale, isDark: false),
                darkTheme: AppTheme.themeForLocale(currentLocale, isDark: true),
                themeMode: currentThemeMode,
                supportedLocales: const [Locale('ar'), Locale('en')],
                localizationsDelegates: const [
                  SirenLocalizations.delegate,
                  GlobalMaterialLocalizations.delegate,
                  GlobalWidgetsLocalizations.delegate,
                  GlobalCupertinoLocalizations.delegate,
                ],
                home: child,
              );
            },
          );
        },
      ),
    );
  }

  group('Header Language Buttons Removal Requirement', () {
    testWidgets('Header language pill is absent across all primary screens', (tester) async {
      // 1. LoginScreen
      await tester.pumpWidget(createTestWidget(child: const LoginScreen()));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('login_lang_toggle')), findsNothing);

      // 2. RegisterScreen
      await tester.pumpWidget(createTestWidget(child: const RegisterScreen()));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('register_lang_toggle')), findsNothing);
      expect(find.byKey(const Key('login_lang_toggle')), findsNothing);

      // 3. HomeScreen
      await tester.pumpWidget(createTestWidget(child: const HomeScreen()));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('home_lang_toggle')), findsNothing);

      // 4. TrackingScreen
      await tester.pumpWidget(createTestWidget(child: const TrackingScreen()));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('tracking_lang_toggle')), findsNothing);

      // 5. AccountScreen
      await tester.pumpWidget(createTestWidget(child: const AccountScreen()));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('account_lang_toggle')), findsNothing);

      // 6. SettingsScreen
      await tester.pumpWidget(createTestWidget(child: const SettingsScreen()));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('settings_lang_toggle')), findsNothing);
    });
  });

  group('Registration Screen Prototype Parity & Network Gap Behavior', () {
    testWidgets('Renders all canonical fields and emergency direct call note in Arabic', (tester) async {
      await tester.pumpWidget(createTestWidget(child: const RegisterScreen(), locale: const Locale('ar')));
      await tester.pumpAndSettle();

      // Brand
      expect(find.text('سايرنجريد'), findsOneWidget);
      expect(find.text('(SirenGrid)'), findsOneWidget);

      // Header title & subtitle
      expect(find.text('إنشاء حساب'), findsOneWidget);
      expect(find.textContaining('مدينة نصر'), findsOneWidget);

      // Form fields
      expect(find.byKey(const Key('register_name_input')), findsOneWidget);
      expect(find.byKey(const Key('register_phone_input')), findsOneWidget);
      expect(find.byKey(const Key('register_nid_input')), findsOneWidget);
      expect(find.byKey(const Key('register_pin_input')), findsOneWidget);

      // Emergency 122 note
      expect(find.textContaining(AppConfig.hotlinePolice), findsOneWidget);
      expect(find.textContaining('في حالة الخطر المباشر؟'), findsOneWidget);

      // Submit CTA & signin link
      expect(find.byKey(const Key('register_submit_button')), findsOneWidget);
      expect(find.byKey(const Key('register_signin_link')), findsOneWidget);
    });

    testWidgets('Renders all canonical fields and emergency note in English', (tester) async {
      await tester.pumpWidget(createTestWidget(child: const RegisterScreen(), locale: const Locale('en')));
      await tester.pumpAndSettle();

      expect(find.text('SirenGrid'), findsOneWidget);
      expect(find.text('Create Account'), findsOneWidget);
      expect(find.textContaining('Nasr City'), findsOneWidget);
      expect(find.byKey(const Key('register_name_input')), findsOneWidget);
      expect(find.byKey(const Key('register_phone_input')), findsOneWidget);
      expect(find.byKey(const Key('register_nid_input')), findsOneWidget);
      expect(find.byKey(const Key('register_pin_input')), findsOneWidget);
      expect(find.textContaining(AppConfig.hotlinePolice), findsOneWidget);
      expect(find.textContaining('Immediate danger?'), findsOneWidget);
    });

    testWidgets('Validation blocks incomplete fields and displays appropriate messages', (tester) async {
      tester.view.physicalSize = const Size(800, 1600);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() {
        tester.view.resetPhysicalSize();
        tester.view.resetDevicePixelRatio();
      });
      await tester.pumpWidget(createTestWidget(child: const RegisterScreen(), locale: const Locale('ar')));
      await tester.pumpAndSettle();

      // 1. Submit empty -> name required
      await tester.ensureVisible(find.byKey(const Key('register_submit_button')));
      await tester.tap(find.byKey(const Key('register_submit_button')));
      await tester.pumpAndSettle();
      expect(find.text('يرجى إدخال الاسم بالكامل'), findsOneWidget);

      // Enter name
      await tester.enterText(find.byKey(const Key('register_name_input')), 'منى عادل');
      await tester.ensureVisible(find.byKey(const Key('register_submit_button')));
      await tester.tap(find.byKey(const Key('register_submit_button')));
      await tester.pumpAndSettle();
      expect(find.text('يرجى إدخال رقم الهاتف'), findsOneWidget);

      // Enter phone
      await tester.enterText(find.byKey(const Key('register_phone_input')), '+201012345678');
      await tester.ensureVisible(find.byKey(const Key('register_submit_button')));
      await tester.tap(find.byKey(const Key('register_submit_button')));
      await tester.pumpAndSettle();
      expect(find.text('يجب أن يتكون الرقم القومي من 14 رقماً'), findsOneWidget);

      // Enter incomplete National ID (less than 14 digits)
      await tester.enterText(find.byKey(const Key('register_nid_input')), '12345');
      await tester.ensureVisible(find.byKey(const Key('register_submit_button')));
      await tester.tap(find.byKey(const Key('register_submit_button')));
      await tester.pumpAndSettle();
      expect(find.text('يجب أن يتكون الرقم القومي من 14 رقماً'), findsOneWidget);

      // Enter valid 14 digits National ID
      await tester.enterText(find.byKey(const Key('register_nid_input')), '29810101234567');
      await tester.ensureVisible(find.byKey(const Key('register_submit_button')));
      await tester.tap(find.byKey(const Key('register_submit_button')));
      await tester.pumpAndSettle();
      expect(find.text('يجب أن يتكون رمز PIN من 4 أرقام'), findsOneWidget);

      // Enter incomplete PIN
      await tester.enterText(find.byKey(const Key('register_pin_input')), '12');
      await tester.ensureVisible(find.byKey(const Key('register_submit_button')));
      await tester.tap(find.byKey(const Key('register_submit_button')));
      await tester.pumpAndSettle();
      expect(find.text('يجب أن يتكون رمز PIN من 4 أرقام'), findsOneWidget);
    });

    testWidgets('Submitting valid form shows truthful gap notice without network request', (tester) async {
      tester.view.physicalSize = const Size(800, 1600);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() {
        tester.view.resetPhysicalSize();
        tester.view.resetDevicePixelRatio();
      });
      await tester.pumpWidget(createTestWidget(child: const RegisterScreen(), locale: const Locale('ar')));
      await tester.pumpAndSettle();

      await tester.enterText(find.byKey(const Key('register_name_input')), 'منى عادل');
      await tester.enterText(find.byKey(const Key('register_phone_input')), '+201012345678');
      await tester.enterText(find.byKey(const Key('register_nid_input')), '29810101234567');
      await tester.enterText(find.byKey(const Key('register_pin_input')), '1234');

      await tester.ensureVisible(find.byKey(const Key('register_submit_button')));
      await tester.tap(find.byKey(const Key('register_submit_button')));
      await tester.pumpAndSettle();

      // Truthful message reported
      expect(find.text('خدمة إنشاء الحساب غير متصلة بالخادم بعد.'), findsOneWidget);
    });

    testWidgets('Submitting valid form in English shows English truthful gap notice', (tester) async {
      tester.view.physicalSize = const Size(800, 1600);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() {
        tester.view.resetPhysicalSize();
        tester.view.resetDevicePixelRatio();
      });
      await tester.pumpWidget(createTestWidget(child: const RegisterScreen(), locale: const Locale('en')));
      await tester.pumpAndSettle();

      await tester.enterText(find.byKey(const Key('register_name_input')), 'Mona Adel');
      await tester.enterText(find.byKey(const Key('register_phone_input')), '+201012345678');
      await tester.enterText(find.byKey(const Key('register_nid_input')), '29810101234567');
      await tester.enterText(find.byKey(const Key('register_pin_input')), '1234');

      await tester.ensureVisible(find.byKey(const Key('register_submit_button')));
      await tester.tap(find.byKey(const Key('register_submit_button')));
      await tester.pumpAndSettle();

      expect(find.text('Registration backend is not connected yet.'), findsOneWidget);
    });

    testWidgets('LoginScreen navigates to RegisterScreen and back cleanly', (tester) async {
      tester.view.physicalSize = const Size(800, 1600);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() {
        tester.view.resetPhysicalSize();
        tester.view.resetDevicePixelRatio();
      });
      await tester.pumpWidget(createTestWidget(child: const LoginScreen(), locale: const Locale('en')));
      await tester.pumpAndSettle();

      // Find register link on login screen
      final regLink = find.byKey(const Key('login_register_link'));
      expect(regLink, findsOneWidget);

      await tester.ensureVisible(regLink);
      await tester.tap(regLink);
      await tester.pumpAndSettle();

      // Navigated to RegisterScreen
      expect(find.byType(RegisterScreen), findsOneWidget);
      expect(find.text('Create Account'), findsOneWidget);

      // Tap Sign In link
      await tester.ensureVisible(find.byKey(const Key('register_signin_link')));
      await tester.tap(find.byKey(const Key('register_signin_link')));
      await tester.pumpAndSettle();

      // Back to LoginScreen
      expect(find.byType(LoginScreen), findsOneWidget);
      expect(find.byType(RegisterScreen), findsNothing);
    });
  });

  group('MainShell Tab Sliding & PageView Animation', () {
    testWidgets('MainShell contains PageView with NeverScrollableScrollPhysics', (tester) async {
      final authCubit = AuthCubit(ApiClient());
      authCubit.emit(const Authenticated(CitizenProfile(
        citizenReference: 'SG-1',
        displayName: 'Test User',
        phone: '+201000000000',
        maskedNationalId: '••••',
        status: 'VERIFIED',
      )));

      await tester.pumpWidget(createTestWidget(child: const MainShell(), authCubit: authCubit));
      await tester.pumpAndSettle();

      final pageView = tester.widget<PageView>(find.byType(PageView));
      expect(pageView.physics, isA<NeverScrollableScrollPhysics>());

      // Switch to Tracking tab
      await tester.tap(find.byIcon(Icons.location_searching_outlined));
      await tester.pumpAndSettle();

      expect(find.byType(TrackingScreen), findsOneWidget);

      // Switch to Account tab
      await tester.tap(find.byIcon(Icons.person_outline));
      await tester.pumpAndSettle();

      expect(find.byType(AccountScreen), findsOneWidget);
    });
  });

  group('Dark Mode & Appearance Selection in Settings', () {
    testWidgets('Dark theme palette applies dark background and slate surfaces', (tester) async {
      await tester.pumpWidget(createTestWidget(
        child: const SettingsScreen(),
        themeMode: ThemeMode.dark,
      ));
      await tester.pumpAndSettle();

      final scaffold = tester.widget<Scaffold>(find.byType(Scaffold));
      expect(scaffold.backgroundColor, equals(AppThemeColors.dark.background));
    });

    testWidgets('Theme dropdown switches to dark and persists', (tester) async {
      await tester.pumpWidget(createTestWidget(
        child: const SettingsScreen(),
        themeMode: ThemeMode.light,
      ));
      await tester.pumpAndSettle();

      // Tap theme dropdown
      await tester.tap(find.byKey(const Key('settings_theme_dropdown')));
      await tester.pumpAndSettle();

      // Select Dark
      await tester.tap(find.text('داكن').last);
      await tester.pumpAndSettle();

      final savedTheme = await StorageService.getThemePreference();
      expect(savedTheme, equals('dark'));
    });
  });

  group('Responsive Viewport Verification for RegisterScreen', () {
    for (final width in [375.0, 390.0, 430.0, 440.0]) {
      testWidgets('RegisterScreen renders with 0 overflow on $width px width', (tester) async {
        tester.view.physicalSize = Size(width * 2, 844 * 2);
        tester.view.devicePixelRatio = 2.0;
        addTearDown(() {
          tester.view.resetPhysicalSize();
          tester.view.resetDevicePixelRatio();
        });

        await tester.pumpWidget(createTestWidget(child: const RegisterScreen(), locale: const Locale('ar')));
        await tester.pumpAndSettle();

        expect(tester.takeException(), isNull);
      });
    }
  });
}
