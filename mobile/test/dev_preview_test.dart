import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:sirengrid_citizen/app/app.dart';
import 'package:sirengrid_citizen/app/shell.dart';
import 'package:sirengrid_citizen/core/api_client.dart';
import 'package:sirengrid_citizen/core/config.dart';
import 'package:sirengrid_citizen/core/localization/locale_cubit.dart';
import 'package:sirengrid_citizen/core/localization/siren_localizations.dart';
import 'package:sirengrid_citizen/core/services.dart';
import 'package:sirengrid_citizen/features/account/account_screen.dart';
import 'package:sirengrid_citizen/features/auth/auth_cubit.dart';
import 'package:sirengrid_citizen/features/auth/login_screen.dart';
import 'package:sirengrid_citizen/features/emergency_home/emergency_service.dart';
import 'package:sirengrid_citizen/features/emergency_home/home_cubit.dart';
import 'package:sirengrid_citizen/features/emergency_home/widgets/confirmation_sheet.dart';
import 'package:sirengrid_citizen/features/tracking/tracking_cubit.dart';
import 'package:sirengrid_citizen/features/tracking/tracking_screen.dart';

class MockHttpClient extends http.BaseClient {
  final Future<http.Response> Function(http.BaseRequest request) handler;
  final List<http.BaseRequest> requests = [];

  MockHttpClient(this.handler);

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    requests.add(request);
    final response = await handler(request);
    return http.StreamedResponse(
      Stream.value(response.bodyBytes),
      response.statusCode,
      headers: response.headers,
    );
  }
}

void main() {
  setUp(() {
    StorageService.enableMockStorage();
    AppConfig.overridePreviewAllowed = null;
  });

  tearDown(() {
    StorageService.resetStorage();
    AppConfig.overridePreviewAllowed = null;
  });

  Widget createTestWidget({
    required Widget child,
    AuthCubit? authCubit,
    HomeCubit? homeCubit,
    TrackingCubit? trackingCubit,
    Locale locale = const Locale('en'),
    ApiClient? apiClient,
  }) {
    final client = apiClient ?? ApiClient(client: MockHttpClient((_) async => http.Response('{}', 200)));
    return MultiBlocProvider(
      key: UniqueKey(),
      providers: [
        BlocProvider<LocaleCubit>(create: (_) => LocaleCubit(locale)),
        BlocProvider<AuthCubit>(create: (_) => authCubit ?? AuthCubit(client)),
        BlocProvider<HomeCubit>(create: (_) => homeCubit ?? HomeCubit(client)),
        BlocProvider<TrackingCubit>(create: (_) => trackingCubit ?? TrackingCubit(client)),
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
            home: Scaffold(body: child),
          );
        },
      ),
    );
  }

  group('Requirement 1 & 2: Preview Button Rendering & Production Guarding', () {
    testWidgets('1a. Preview button is rendered when dev mode is active in English', (tester) async {
      AppConfig.overridePreviewAllowed = true;

      await tester.pumpWidget(createTestWidget(
        child: const LoginScreen(),
        locale: const Locale('en'),
      ));
      await tester.pumpAndSettle();

      final enBtn = find.byKey(const Key('login_preview_button'));
      expect(enBtn, findsOneWidget);
      expect(find.text('Preview App (Dev Only)'), findsOneWidget);
    });

    testWidgets('1b. Preview button is rendered when dev mode is active in Arabic', (tester) async {
      AppConfig.overridePreviewAllowed = true;

      await tester.pumpWidget(createTestWidget(
        child: const LoginScreen(),
        locale: const Locale('ar'),
      ));
      await tester.pumpAndSettle();

      final arBtn = find.byKey(const Key('login_preview_button'));
      expect(arBtn, findsOneWidget);
      expect(find.text('معاينة التطبيق (تطوير فقط)'), findsOneWidget);
    });

    testWidgets('2. Preview button is NOT rendered in release/production configuration', (tester) async {
      AppConfig.overridePreviewAllowed = false;

      await tester.pumpWidget(createTestWidget(
        child: const LoginScreen(),
        locale: const Locale('en'),
      ));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('login_preview_button')), findsNothing);
      expect(find.text('Preview App (Dev Only)'), findsNothing);
      expect(find.text('معاينة التطبيق (تطوير فقط)'), findsNothing);
    });

    test('2b. enterPreviewMode is a no-op when preview mode is not allowed', () {
      AppConfig.overridePreviewAllowed = false;
      final client = ApiClient(client: MockHttpClient((_) async => http.Response('{}', 200)));
      final cubit = AuthCubit(client);

      cubit.enterPreviewMode();
      expect(cubit.state, isA<AuthInitial>());
    });
  });

  group('Requirement 3: Isolated Preview Auth State & Network Safety', () {
    test('3. Entering preview mode emits isolated preview state without saving token', () async {
      AppConfig.overridePreviewAllowed = true;
      final mock = MockHttpClient((_) async => http.Response('{}', 200));
      final client = ApiClient(client: mock);
      final cubit = AuthCubit(client);

      cubit.enterPreviewMode();

      expect(cubit.state, isA<AuthPreview>());
      final previewState = cubit.state as AuthPreview;
      expect(previewState.profile.displayName, equals('Demo Citizen'));
      expect(previewState.profile.phone, equals('+20 100 000 0000'));
      expect(previewState.profile.maskedNationalId, equals('•••• •••• •••• 0000'));
      expect(previewState.profile.status, equals('Verified'));
      expect(previewState.profile.dataReality, equals('SIMULATED'));

      // Storage & network isolation guarantees
      final token = await StorageService.getSessionCredential();
      expect(token, isNull);
      expect(client.hasSessionCredential, isFalse);
      expect(mock.requests, isEmpty);
    });
  });

  group('Requirement 4: Emergency Confirmation Block in Preview Mode', () {
    testWidgets('4. Final Confirm in preview mode blocks emergency submission and shows localized notice (en)', (tester) async {
      final mock = MockHttpClient((_) async => http.Response('{}', 200));
      final client = ApiClient(client: mock);
      final authCubit = AuthCubit(client)..enterPreviewMode();
      final homeCubit = HomeCubit(client);

      bool emergencySubmittedCalled = false;
      await tester.pumpWidget(createTestWidget(
        apiClient: client,
        authCubit: authCubit,
        homeCubit: homeCubit,
        locale: const Locale('en'),
        child: Builder(
          builder: (ctx) => ElevatedButton(
            key: const Key('open_sheet_btn'),
            onPressed: () {
              ConfirmationSheet.show(
                context: ctx,
                service: EmergencyService.all[0], // Ambulance
                onSubmitted: (_) => emergencySubmittedCalled = true,
              );
            },
            child: const Text('Open'),
          ),
        ),
      ));
      await tester.pumpAndSettle();

      // Open sheet
      await tester.tap(find.byKey(const Key('open_sheet_btn')));
      await tester.pumpAndSettle();

      // Click Confirm Button
      final confirmBtn = find.byKey(const Key('confirm_sheet_submit_button'));
      expect(confirmBtn, findsOneWidget);
      await tester.tap(confirmBtn);
      await tester.pumpAndSettle();

      // Verify submission was BLOCKED
      expect(emergencySubmittedCalled, isFalse);
      expect(mock.requests, isEmpty); // Zero POST requests

      // Verify localized banner and snackbar appear
      expect(find.byKey(const Key('confirm_preview_banner')), findsOneWidget);
      expect(find.text('Emergency submission is disabled in UI Preview Mode.'), findsAtLeastNWidgets(1));
    });

    testWidgets('4b. Final Confirm in preview mode blocks submission in Arabic', (tester) async {
      final mock = MockHttpClient((_) async => http.Response('{}', 200));
      final client = ApiClient(client: mock);
      final authCubit = AuthCubit(client)..enterPreviewMode();
      final homeCubit = HomeCubit(client);

      await tester.pumpWidget(createTestWidget(
        apiClient: client,
        authCubit: authCubit,
        homeCubit: homeCubit,
        locale: const Locale('ar'),
        child: Builder(
          builder: (ctx) => ElevatedButton(
            key: const Key('open_sheet_btn'),
            onPressed: () {
              ConfirmationSheet.show(
                context: ctx,
                service: EmergencyService.all[0],
              );
            },
            child: const Text('Open'),
          ),
        ),
      ));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('open_sheet_btn')));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('confirm_sheet_submit_button')));
      await tester.pumpAndSettle();

      expect(mock.requests, isEmpty);
      expect(find.text('إرسال البلاغ غير متاح في وضع معاينة الواجهة.'), findsAtLeastNWidgets(1));
    });
  });

  group('Requirement 5: Tracking Preview Toggle Without Network Requests', () {
    testWidgets('5. Tracking preview toggle switches views without network requests', (tester) async {
      final mock = MockHttpClient((_) async => http.Response('{}', 200));
      final client = ApiClient(client: mock);
      final authCubit = AuthCubit(client)..enterPreviewMode();

      await tester.pumpWidget(createTestWidget(
        apiClient: client,
        authCubit: authCubit,
        locale: const Locale('en'),
        child: const TrackingScreen(),
      ));
      await tester.pumpAndSettle();

      // Zero network requests made on mount
      expect(mock.requests, isEmpty);

      // Verify preview toggle bar is present
      expect(find.byKey(const Key('tracking_preview_toggle_bar')), findsOneWidget);
      expect(find.byKey(const Key('tracking_preview_empty_btn')), findsOneWidget);
      expect(find.byKey(const Key('tracking_preview_active_btn')), findsOneWidget);

      // Initial state is Empty View
      expect(find.text('No active request'), findsOneWidget);

      // Switch to Active Request Preview
      await tester.tap(find.byKey(const Key('tracking_preview_active_btn')));
      await tester.pumpAndSettle();

      // Active view rendered with static preview data
      expect(find.text('Ambulance Request'), findsOneWidget);
      expect(find.text('EN_ROUTE (En Route)'), findsOneWidget);
      expect(find.text('~4 min'), findsOneWidget);
      expect(find.textContaining('Ambulance 14'), findsOneWidget);
      expect(find.text('Simulated Tracking • Simulation Mode'), findsOneWidget);

      // Still zero network requests
      expect(mock.requests, isEmpty);

      // Switch back to Empty State via empty button
      await tester.tap(find.byKey(const Key('tracking_preview_empty_btn')));
      await tester.pumpAndSettle();

      expect(find.text('No active request'), findsOneWidget);

      // Switch to active again and test "Show Empty State" bottom button
      await tester.tap(find.byKey(const Key('tracking_preview_active_btn')));
      await tester.pumpAndSettle();
      expect(find.text('Ambulance Request'), findsOneWidget);

      await tester.drag(find.byType(ListView), const Offset(0, -400));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('tracking_view_empty_btn')));
      await tester.pumpAndSettle();
      expect(find.text('No active request'), findsOneWidget);

      // Storage untouched
      expect(await StorageService.getActiveRequestId(), isNull);
      expect(mock.requests, isEmpty);
    });
  });

  group('Requirement 6: Account Preview & Sign Out to LoginScreen', () {
    testWidgets('6. Account screen displays preview profile and Sign Out returns to Login', (tester) async {
      AppConfig.overridePreviewAllowed = true;
      final mock = MockHttpClient((_) async => http.Response('{}', 200));
      final client = ApiClient(client: mock);
      final authCubit = AuthCubit(client)..enterPreviewMode();

      await tester.pumpWidget(createTestWidget(
        apiClient: client,
        authCubit: authCubit,
        locale: const Locale('en'),
        child: const AccountScreen(),
      ));
      await tester.pumpAndSettle();

      // Verify Demo Citizen profile data
      expect(find.text('Demo Citizen'), findsOneWidget);
      expect(find.text('+20 100 000 0000'), findsOneWidget);
      expect(find.text('•••• •••• •••• 0000'), findsOneWidget);
      expect(find.text('preview-citizen'), findsOneWidget);
      expect(find.text('Verified'), findsOneWidget);
      expect(find.text('Simulated Data'), findsOneWidget);
      expect(find.text('Unavailable'), findsOneWidget); // Registered Address gap
      expect(find.text('Not checked yet'), findsOneWidget); // Notification status

      // Scroll to Sign Out button
      await tester.drag(find.byType(ListView), const Offset(0, -300));
      await tester.pumpAndSettle();

      // Tap Sign Out
      final signOutBtn = find.byKey(const Key('account_sign_out_btn'));
      expect(signOutBtn, findsOneWidget);
      await tester.tap(signOutBtn);
      await tester.pumpAndSettle();

      // State is now Unauthenticated
      expect(authCubit.state, isA<Unauthenticated>());

      // Zero logout network calls in preview mode
      expect(mock.requests, isEmpty);
    });

    testWidgets('6b. Full SirenGridCitizenApp integrates dev preview and exit preview cleanly', (tester) async {
      AppConfig.overridePreviewAllowed = true;
      final mock = MockHttpClient((_) async => http.Response('{}', 200));
      final client = ApiClient(client: mock);

      await tester.pumpWidget(SirenGridCitizenApp(apiClient: client));
      await tester.pumpAndSettle();

      // Starts at LoginScreen
      expect(find.byKey(const Key('login_preview_button')), findsOneWidget);

      // Enter Preview Mode
      await tester.tap(find.byKey(const Key('login_preview_button')));
      await tester.pumpAndSettle();

      // Enters MainShell (Home tab)
      expect(find.byType(MainShell), findsOneWidget);
      expect(find.textContaining('Demo Citizen'), findsOneWidget);

      // Switch to Account tab
      await tester.tap(find.byIcon(Icons.person_outline));
      await tester.pumpAndSettle();

      // Scroll to Sign out button
      await tester.drag(find.byType(ListView), const Offset(0, -300));
      await tester.pumpAndSettle();

      // Sign out
      await tester.tap(find.byKey(const Key('account_sign_out_btn')));
      await tester.pumpAndSettle();

      // Cleanly returned to LoginScreen
      expect(find.byType(LoginScreen), findsOneWidget);
      expect(find.byKey(const Key('login_preview_button')), findsOneWidget);
    });
  });
}
