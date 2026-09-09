import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:sirengrid_citizen/app/shell.dart';
import 'package:sirengrid_citizen/core/api_client.dart';
import 'package:sirengrid_citizen/core/localization/locale_cubit.dart';
import 'package:sirengrid_citizen/core/localization/siren_localizations.dart';
import 'package:sirengrid_citizen/core/services.dart';
import 'package:sirengrid_citizen/core/theme.dart';
import 'package:sirengrid_citizen/features/auth/auth_cubit.dart';
import 'package:sirengrid_citizen/features/auth/login_screen.dart';

import 'package:sirengrid_citizen/features/emergency_home/home_cubit.dart';
import 'package:sirengrid_citizen/features/tracking/tracking_cubit.dart';

// ponytail: lightweight standard mock client for UI integration tests
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

Widget createTestApp({
  required ApiClient apiClient,
  required AuthCubit authCubit,
  LocaleCubit? localeCubit,
}) {
  return MultiBlocProvider(
    providers: [
      BlocProvider<LocaleCubit>(create: (_) => localeCubit ?? LocaleCubit()),
      BlocProvider<AuthCubit>.value(value: authCubit),
      BlocProvider<HomeCubit>(create: (_) => HomeCubit(apiClient)),
      BlocProvider<TrackingCubit>(create: (_) => TrackingCubit(apiClient)),
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
          home: BlocBuilder<AuthCubit, AuthState>(
            builder: (context, state) {
              if (state is Authenticated) {
                return const MainShell();
              }
              if (state is AuthCheckingSession || state is AuthInitial) {
                return const Scaffold(
                  key: Key('app_splash_screen'),
                  body: Center(child: CircularProgressIndicator()),
                );
              }
              if (state is AuthFailure && state.isSessionCheckFailure) {
                return Scaffold(
                  key: const Key('app_session_error_screen'),
                  body: Center(
                    child: Text(state.message),
                  ),
                );
              }
              return const LoginScreen();
            },
          ),
        );
      },
    ),
  );
}

void main() {
  setUp(() {
    StorageService.enableMockStorage();
  });

  tearDown(() {
    StorageService.resetStorage();
  });

  group('App Start & Session Routing', () {
    testWidgets('unauthenticated state shows LoginScreen', (tester) async {
      final client = ApiClient();
      final authCubit = AuthCubit(client);

      await tester.pumpWidget(createTestApp(apiClient: client, authCubit: authCubit));
      authCubit.emit(const Unauthenticated());
      await tester.pumpAndSettle();

      expect(find.byType(LoginScreen), findsOneWidget);
      expect(find.byType(MainShell), findsNothing);
    });

    testWidgets('authenticated state shows MainShell', (tester) async {
      final client = ApiClient();
      final authCubit = AuthCubit(client);

      await tester.pumpWidget(createTestApp(apiClient: client, authCubit: authCubit));

      const profile = CitizenProfile(
        citizenReference: 'cit-101',
        displayName: 'Ahmed Mansour',
        phone: '+201001234567',
        maskedNationalId: '•••• •••• •••• 4821',
        status: 'Verified',
        dataReality: 'SYNTHETIC',
      );

      authCubit.emit(const Authenticated(profile));
      await tester.pumpAndSettle();

      expect(find.byType(MainShell), findsOneWidget);
      expect(find.byType(LoginScreen), findsNothing);
    });

    testWidgets('session-check shows minimal loading/splash state', (tester) async {
      final client = ApiClient();
      final authCubit = AuthCubit(client);

      await tester.pumpWidget(createTestApp(apiClient: client, authCubit: authCubit));
      authCubit.emit(const AuthCheckingSession());
      await tester.pump();

      expect(find.byKey(const Key('app_splash_screen')), findsOneWidget);
      expect(find.byType(LoginScreen), findsNothing);
      expect(find.byType(MainShell), findsNothing);
    });

    testWidgets('session-check connectivity failure shows truthful error screen without destroying session', (tester) async {
      await StorageService.saveSessionCredential('persisted-session-token');

      final client = ApiClient();
      final authCubit = AuthCubit(client);

      await tester.pumpWidget(createTestApp(apiClient: client, authCubit: authCubit));
      authCubit.emit(const AuthFailure('Unable to connect to SirenGrid server.', isSessionCheckFailure: true));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('app_session_error_screen')), findsOneWidget);
      expect(find.text('Unable to connect to SirenGrid server.'), findsOneWidget);
      // Credential must remain in secure storage
      expect(await StorageService.hasSessionCredential(), isTrue);
    });
  });

  group('LoginScreen Form & Submission Behavior', () {
    testWidgets('submitting phone and PIN calls AuthCubit and transitions to Authenticated', (tester) async {
      String? submittedPhone;
      String? submittedPin;

      final mockHttp = MockHttpClient((request) async {
        if (request.url.path == '/api/v1/mobile/auth/login') {
          final body = jsonDecode((request as http.Request).body) as Map<String, dynamic>;
          submittedPhone = body['phone'] as String?;
          submittedPin = body['pin'] as String?;
          return http.Response(
            jsonEncode({'access_token': 'test-session-token'}),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        if (request.url.path == '/api/v1/mobile/me') {
          return http.Response(
            jsonEncode({
              'citizen_reference': 'cit-test',
              'display_name': 'Sarah Adel',
              'phone': '+201011223344',
              'national_id_masked': '**********5566',
              'identity_status': 'Verified',
              'data_reality': 'DEMO',
            }),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('Not Found', 404);
      });

      final client = ApiClient(client: mockHttp);
      final authCubit = AuthCubit(client);

      await tester.pumpWidget(createTestApp(apiClient: client, authCubit: authCubit));
      authCubit.emit(const Unauthenticated());
      await tester.pumpAndSettle();

      // Enter phone and PIN
      await tester.enterText(find.byKey(const Key('login_phone_field')), '+201011223344');
      await tester.enterText(find.byKey(const Key('login_pin_field')), '1234');
      await tester.pump();

      // Tap submit button
      await tester.tap(find.byKey(const Key('login_submit_button')));
      await tester.pumpAndSettle();

      expect(submittedPhone, equals('+201011223344'));
      expect(submittedPin, equals('1234'));
      expect(authCubit.state, isA<Authenticated>());
      expect(find.byType(MainShell), findsOneWidget);
    });

    testWidgets('loading state prevents duplicate submission and shows progress indicator', (tester) async {
      final client = ApiClient();
      final authCubit = AuthCubit(client);

      await tester.pumpWidget(createTestApp(apiClient: client, authCubit: authCubit));
      authCubit.emit(const Authenticating());
      await tester.pump();

      final button = tester.widget<ElevatedButton>(find.byKey(const Key('login_submit_button')));
      expect(button.onPressed, isNull); // Disabled while loading
      expect(find.byType(CircularProgressIndicator), findsOneWidget);
    });

    testWidgets('authentication failure displays inline error banner', (tester) async {
      final client = ApiClient();
      final authCubit = AuthCubit(client);

      await tester.pumpWidget(createTestApp(apiClient: client, authCubit: authCubit));
      authCubit.emit(const AuthFailure('Invalid credentials. Please check your phone and PIN.'));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('login_error_banner')), findsOneWidget);
      expect(find.text('Invalid credentials. Please check your phone and PIN.'), findsOneWidget);
      expect(find.byType(LoginScreen), findsOneWidget);
    });
  });

  group('Localization, Layout & Strict Field Compliance', () {
    testWidgets('Arabic locale renders RTL directionality and Arabic brand hierarchy', (tester) async {
      final client = ApiClient();
      final authCubit = AuthCubit(client);
      final localeCubit = LocaleCubit()..setLocale(const Locale('ar'));

      await tester.pumpWidget(createTestApp(
        apiClient: client,
        authCubit: authCubit,
        localeCubit: localeCubit,
      ));
      authCubit.emit(const Unauthenticated());
      await tester.pumpAndSettle();

      // Verify Directionality is RTL
      final textDirection = Directionality.of(tester.element(find.byType(LoginScreen)));
      expect(textDirection, equals(TextDirection.rtl));

      // Brand hierarchy: سايرنجريد and (SirenGrid)
      expect(find.text('سايرنجريد'), findsOneWidget);
      expect(find.text('(SirenGrid)'), findsOneWidget);
      expect(find.text('تسجيل الدخول'), findsAtLeastNWidgets(1));
      expect(find.text('رقم الهاتف'), findsOneWidget);
      expect(find.text('رمز PIN'), findsOneWidget);
      expect(find.byKey(const Key('login_lang_toggle')), findsNothing); // Toggle removed from header per spec
    });

    testWidgets('English locale renders LTR directionality and English labels', (tester) async {
      final client = ApiClient();
      final authCubit = AuthCubit(client);
      final localeCubit = LocaleCubit()..setLocale(const Locale('en'));

      await tester.pumpWidget(createTestApp(
        apiClient: client,
        authCubit: authCubit,
        localeCubit: localeCubit,
      ));
      authCubit.emit(const Unauthenticated());
      await tester.pumpAndSettle();

      final textDirection = Directionality.of(tester.element(find.byType(LoginScreen)));
      expect(textDirection, equals(TextDirection.ltr));

      // Brand title in English
      expect(find.text('SirenGrid'), findsOneWidget);
      expect(find.text('Sign In'), findsAtLeastNWidgets(1));
      expect(find.text('Phone Number'), findsOneWidget);
      expect(find.text('PIN'), findsOneWidget);
      expect(find.byKey(const Key('login_lang_toggle')), findsNothing); // Toggle removed from header per spec
    });

    testWidgets('Phone and PIN fields remain LTR even when application locale is Arabic RTL', (tester) async {
      final client = ApiClient();
      final authCubit = AuthCubit(client);
      final localeCubit = LocaleCubit()..setLocale(const Locale('ar'));

      await tester.pumpWidget(createTestApp(
        apiClient: client,
        authCubit: authCubit,
        localeCubit: localeCubit,
      ));
      authCubit.emit(const Unauthenticated());
      await tester.pumpAndSettle();

      // Check phone field directionality
      final phoneFieldDirection = tester.widget<Directionality>(
        find.ancestor(
          of: find.byKey(const Key('login_phone_field')),
          matching: find.byType(Directionality),
        ).first,
      );
      expect(phoneFieldDirection.textDirection, equals(TextDirection.ltr));

      // Check PIN field directionality
      final pinFieldDirection = tester.widget<Directionality>(
        find.ancestor(
          of: find.byKey(const Key('login_pin_field')),
          matching: find.byType(Directionality),
        ).first,
      );
      expect(pinFieldDirection.textDirection, equals(TextDirection.ltr));
    });

    testWidgets('no National ID field exists on LoginScreen', (tester) async {
      final client = ApiClient();
      final authCubit = AuthCubit(client);

      await tester.pumpWidget(createTestApp(apiClient: client, authCubit: authCubit));
      authCubit.emit(const Unauthenticated());
      await tester.pumpAndSettle();

      expect(find.text('الرقم القومي'), findsNothing);
      expect(find.text('National ID'), findsNothing);
      expect(find.byKey(const Key('login_nid_field')), findsNothing);
    });

    testWidgets('no emergency hotline banner exists on LoginScreen', (tester) async {
      final client = ApiClient();
      final authCubit = AuthCubit(client);

      await tester.pumpWidget(createTestApp(apiClient: client, authCubit: authCubit));
      authCubit.emit(const Unauthenticated());
      await tester.pumpAndSettle();

      // Canonical Arabic sign-in has no emergency footer or hotline banner
      expect(find.textContaining('122'), findsNothing);
      expect(find.textContaining('123'), findsNothing);
      expect(find.textContaining('180'), findsNothing);
      expect(find.textContaining('اتصل الآن'), findsNothing);
      expect(find.textContaining('Call Now'), findsNothing);
    });
  });

  group('LoginScreen Responsive Viewport & Overflow Regression Verification', () {
    const viewports = [
      Size(375, 812), // iPhone mini / standard small
      Size(390, 844), // iPhone 12/13/14
      Size(430, 932), // iPhone 14/15 Pro Max
      Size(440, 956), // iPhone 16 Pro Max
    ];

    for (final size in viewports) {
      for (final lang in ['ar', 'en']) {
        testWidgets('Zero overflow on ${size.width}x${size.height} ($lang) with long error banner', (tester) async {
          tester.view.physicalSize = size;
          tester.view.devicePixelRatio = 1.0;
          addTearDown(() {
            tester.view.resetPhysicalSize();
            tester.view.resetDevicePixelRatio();
          });

          final client = ApiClient();
          final authCubit = AuthCubit(client);
          final localeCubit = LocaleCubit()..setLocale(Locale(lang));

          await tester.pumpWidget(createTestApp(
            apiClient: client,
            authCubit: authCubit,
            localeCubit: localeCubit,
          ));
          authCubit.emit(const AuthFailure(
            'Connection error: Unable to reach SirenGrid server (ClientException: Failed to fetch, uri=http://localhost:8000/api/v1/mobile/auth/login)',
          ));
          await tester.pumpAndSettle();

          expect(tester.takeException(), isNull);
          expect(find.byKey(const Key('login_error_banner')), findsOneWidget);
          expect(find.byKey(const Key('login_submit_button')), findsOneWidget);
        });
      }
    }
  });
}
