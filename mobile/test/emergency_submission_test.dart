import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator/geolocator.dart';
import 'package:http/http.dart' as http;
import 'package:sirengrid_citizen/app/shell.dart';
import 'package:sirengrid_citizen/core/api_client.dart';
import 'package:sirengrid_citizen/core/localization/locale_cubit.dart';
import 'package:sirengrid_citizen/core/localization/siren_localizations.dart';
import 'package:sirengrid_citizen/core/services.dart';
import 'package:sirengrid_citizen/features/auth/auth_cubit.dart';
import 'package:sirengrid_citizen/features/emergency_home/emergency_service.dart';
import 'package:sirengrid_citizen/features/emergency_home/home_cubit.dart';
import 'package:sirengrid_citizen/features/emergency_home/home_screen.dart';
import 'package:sirengrid_citizen/features/emergency_home/widgets/confirmation_sheet.dart';
import 'package:sirengrid_citizen/features/tracking/tracking_cubit.dart';
import 'package:sirengrid_citizen/features/tracking/tracking_screen.dart';

// ponytail: lightweight standard mock client without third-party mock framework
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
  final testPosition = Position(
    latitude: 30.0561,
    longitude: 31.3452,
    timestamp: DateTime(2026, 9, 9, 12, 0, 0),
    accuracy: 12.0,
    altitude: 0.0,
    altitudeAccuracy: 0.0,
    heading: 0.0,
    headingAccuracy: 0.0,
    speed: 0.0,
    speedAccuracy: 0.0,
  );

  const testProfile = CitizenProfile(
    citizenReference: 'cit-nasr-001',
    displayName: 'Amina Nour',
    phone: '+201099887766',
    maskedNationalId: '•••• •••• •••• 4321',
    status: 'Verified',
  );

  setUp(() {
    StorageService.enableMockStorage();
    LocationService.enableMockLocation(
      position: testPosition,
      serviceEnabled: true,
      permission: LocationPermission.whileInUse,
    );
  });

  tearDown(() {
    StorageService.resetStorage();
    LocationService.resetMockLocation();
  });

  group('Service Enum & Frozen Contract Mapping', () {
    test('UI service types map explicitly to Master Plan §14.1 backend enum strings', () {
      expect(EmergencyService.all[0].backendServiceCode, equals('AMBULANCE'));
      expect(EmergencyService.all[1].backendServiceCode, equals('FIRE'));
      expect(EmergencyService.all[2].backendServiceCode, equals('POLICE'));
      expect(EmergencyService.all[3].backendServiceCode, equals('GENERAL'));
    });

    test('fromBackendCode resolves valid EmergencyService instances', () {
      expect(EmergencyService.fromBackendCode('AMBULANCE').id, equals('ambulance'));
      expect(EmergencyService.fromBackendCode('FIRE').id, equals('fire'));
      expect(EmergencyService.fromBackendCode('POLICE').id, equals('police'));
      expect(EmergencyService.fromBackendCode('GENERAL').id, equals('general'));
    });

    test('Submission constructs exact frozen request payload', () async {
      Map<String, dynamic>? capturedPayload;
      String? capturedIdempotencyKey;
      String? capturedAuthHeader;

      final mockClient = MockHttpClient((req) async {
        if (req.url.path == '/api/v1/mobile/emergency-requests') {
          capturedIdempotencyKey = req.headers['Idempotency-Key'];
          capturedAuthHeader = req.headers['Authorization'];
          final bodyString = (req as http.Request).body;
          capturedPayload = jsonDecode(bodyString) as Map<String, dynamic>;

          return http.Response(
            jsonEncode({
              'request_id': 'req-auth-9988',
              'incident_id': 'inc-auth-1234',
              'status': 'RECEIVED',
              'service': 'AMBULANCE',
              'received_at': '2026-09-09T12:00:01Z',
              'tracking_available': true,
            }),
            201,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('Not Found', 404);
      });

      final apiClient = ApiClient(client: mockClient, sessionCredential: 'token-sirengrid-xyz');
      final cubit = HomeCubit(apiClient);

      await cubit.submitEmergency(
        service: EmergencyService.all[0], // Ambulance
        citizenReference: 'cit-nasr-001',
      );

      expect(cubit.state, isA<HomeSubmitted>());
      final submitted = cubit.state as HomeSubmitted;
      expect(submitted.requestId, equals('req-auth-9988'));

      // Check exact payload fields per Master Plan 14.1
      expect(capturedPayload, isNotNull);
      expect(capturedPayload!.containsKey('citizen_reference'), isFalse);
      expect(capturedPayload!['service'], equals('AMBULANCE'));
      expect(capturedPayload!['location'], isA<Map>());
      expect(capturedPayload!['location']['lat'], equals(30.0561));
      expect(capturedPayload!['location']['lon'], equals(31.3452));
      expect(capturedPayload!['location_accuracy_m'], equals(12.0));
      expect(capturedPayload!['client_timestamp'], isNotNull);
      expect(capturedPayload!['note'], isNull);

      // Check headers
      expect(capturedIdempotencyKey, isNotNull);
      expect(RegExp(r'^[0-9a-fA-F-]{36}$').hasMatch(capturedIdempotencyKey!), isTrue);
      expect(capturedAuthHeader, equals('Bearer token-sirengrid-xyz'));
    });

    test('Contract mismatch: missing request_id fails with contractMismatch error, zero fake fallback', () async {
      final mockClient = MockHttpClient((req) async {
        return http.Response(
          jsonEncode({
            'status': 'RECEIVED',
            // Missing 'request_id'!
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      });

      final apiClient = ApiClient(client: mockClient);
      final cubit = HomeCubit(apiClient);

      await cubit.submitEmergency(service: EmergencyService.all[0]);

      expect(cubit.state, isA<HomeError>());
      final err = cubit.state as HomeError;
      expect(err.errorType, equals(HomeErrorType.contractMismatch));
      expect(err.message, contains('Missing authoritative request_id'));
      expect(await StorageService.getActiveRequestId(), isNull);
    });
  });

  group('GPS & Location Service Error Handling', () {
    test('Location services disabled emits location error', () async {
      LocationService.enableMockLocation(
        serviceEnabled: false,
      );

      final apiClient = ApiClient(client: MockHttpClient((_) async => http.Response('ok', 200)));
      final cubit = HomeCubit(apiClient);

      await cubit.submitEmergency(service: EmergencyService.all[0]);

      expect(cubit.state, isA<HomeError>());
      final err = cubit.state as HomeError;
      expect(err.errorType, equals(HomeErrorType.location));
      expect(err.message, contains('Location services are disabled'));
    });

    test('Permission denied emits location error', () async {
      LocationService.enableMockLocation(
        serviceEnabled: true,
        permission: LocationPermission.denied,
      );

      final apiClient = ApiClient(client: MockHttpClient((_) async => http.Response('ok', 200)));
      final cubit = HomeCubit(apiClient);

      await cubit.submitEmergency(service: EmergencyService.all[0]);

      expect(cubit.state, isA<HomeError>());
      final err = cubit.state as HomeError;
      expect(err.errorType, equals(HomeErrorType.location));
      expect(err.message, contains('Location permission is required'));
    });

    test('Permission permanently denied emits location error', () async {
      LocationService.enableMockLocation(
        serviceEnabled: true,
        permission: LocationPermission.deniedForever,
      );

      final apiClient = ApiClient(client: MockHttpClient((_) async => http.Response('ok', 200)));
      final cubit = HomeCubit(apiClient);

      await cubit.submitEmergency(service: EmergencyService.all[0]);

      expect(cubit.state, isA<HomeError>());
      final err = cubit.state as HomeError;
      expect(err.errorType, equals(HomeErrorType.location));
      expect(err.message, contains('permanently denied'));
    });

    test('Location acquisition timeout emits location error', () async {
      LocationService.enableMockLocation(
        error: const LocationAcquisitionException('GPS acquisition timed out.'),
      );

      final apiClient = ApiClient(client: MockHttpClient((_) async => http.Response('ok', 200)));
      final cubit = HomeCubit(apiClient);

      await cubit.submitEmergency(service: EmergencyService.all[0]);

      expect(cubit.state, isA<HomeError>());
      final err = cubit.state as HomeError;
      expect(err.errorType, equals(HomeErrorType.location));
      expect(err.message, contains('GPS acquisition timed out'));
    });

    test('Location readiness check correctly identifies readiness states', () async {
      LocationService.enableMockLocation(serviceEnabled: false);
      expect(await LocationService.checkReadiness(), equals(LocationReadinessResult.disabled));

      LocationService.enableMockLocation(serviceEnabled: true, permission: LocationPermission.denied);
      expect(await LocationService.checkReadiness(), equals(LocationReadinessResult.permissionRequired));

      LocationService.enableMockLocation(serviceEnabled: true, permission: LocationPermission.deniedForever);
      expect(await LocationService.checkReadiness(), equals(LocationReadinessResult.permissionDeniedForever));

      LocationService.enableMockLocation(serviceEnabled: true, permission: LocationPermission.whileInUse);
      expect(await LocationService.checkReadiness(), equals(LocationReadinessResult.ready));
    });
  });

  group('Idempotency Lifecycle & Safe Retry', () {
    test('Same UUID is preserved and reused on retry after network timeout', () async {
      final List<String> capturedKeys = [];
      int attempt = 0;

      final mockClient = MockHttpClient((req) async {
        attempt++;
        capturedKeys.add(req.headers['Idempotency-Key']!);

        if (attempt == 1) {
          throw http.ClientException('Connection timeout');
        }

        return http.Response(
          jsonEncode({
            'request_id': 'req-retry-success-123',
            'incident_id': 'inc-123',
            'status': 'RECEIVED',
            'service': 'FIRE',
            'received_at': '2026-09-09T12:00:00Z',
            'tracking_available': true,
          }),
          201,
          headers: {'content-type': 'application/json'},
        );
      });

      final apiClient = ApiClient(client: mockClient);
      final cubit = HomeCubit(apiClient);

      // First attempt (fails with network error)
      await cubit.submitEmergency(service: EmergencyService.all[1]); // Fire
      expect(cubit.state, isA<HomeError>());
      final firstKey = (cubit.state as HomeError).idempotencyKey;
      expect(await StorageService.getPendingIdempotencyKey(), equals(firstKey));

      // Retry attempt
      await cubit.retryLastSubmission();
      expect(cubit.state, isA<HomeSubmitted>());

      // Verifies exact same UUID was sent on both attempts
      expect(capturedKeys.length, equals(2));
      expect(capturedKeys[0], equals(capturedKeys[1]));
      expect(capturedKeys[0], equals(firstKey));

      // After authoritative success: key is cleared, active request ID is stored
      expect(await StorageService.getPendingIdempotencyKey(), isNull);
      expect(await StorageService.getActiveRequestId(), equals('req-retry-success-123'));
    });

    test('New logical submission after reset generates a new UUID', () async {
      final List<String> capturedKeys = [];

      final mockClient = MockHttpClient((req) async {
        capturedKeys.add(req.headers['Idempotency-Key']!);
        return http.Response(
          jsonEncode({
            'request_id': 'req-fresh-1',
            'incident_id': 'inc-1',
            'status': 'RECEIVED',
            'service': 'POLICE',
            'received_at': '2026-09-09T12:00:00Z',
            'tracking_available': true,
          }),
          201,
          headers: {'content-type': 'application/json'},
        );
      });

      final apiClient = ApiClient(client: mockClient);
      final cubit = HomeCubit(apiClient);

      // Submission 1
      await cubit.submitEmergency(service: EmergencyService.all[2]); // Police
      final key1 = capturedKeys.first;

      // Reset
      await cubit.reset();
      expect(await StorageService.getPendingIdempotencyKey(), isNull);

      // Submission 2
      await cubit.submitEmergency(service: EmergencyService.all[2]);
      final key2 = capturedKeys.last;

      expect(key1, isNot(equals(key2)));
    });
  });

  group('Failure HTTP Semantics & Storage Safety', () {
    test('401 emits auth error and does not clear active request ID', () async {
      await StorageService.saveActiveRequestId('existing-active-req');

      final mockClient = MockHttpClient((_) async => http.Response('Unauthorized', 401));
      final apiClient = ApiClient(client: mockClient);
      final cubit = HomeCubit(apiClient);

      await cubit.submitEmergency(service: EmergencyService.all[0]);

      expect(cubit.state, isA<HomeError>());
      expect((cubit.state as HomeError).errorType, equals(HomeErrorType.auth));
      expect(await StorageService.getActiveRequestId(), equals('existing-active-req'));
    });

    test('409 emits conflict error', () async {
      final mockClient = MockHttpClient((_) async => http.Response('Conflict', 409));
      final apiClient = ApiClient(client: mockClient);
      final cubit = HomeCubit(apiClient);

      await cubit.submitEmergency(service: EmergencyService.all[0]);

      expect(cubit.state, isA<HomeError>());
      expect((cubit.state as HomeError).errorType, equals(HomeErrorType.conflict));
    });

    test('500 emits server error', () async {
      final mockClient = MockHttpClient((_) async => http.Response('Internal Server Error', 500));
      final apiClient = ApiClient(client: mockClient);
      final cubit = HomeCubit(apiClient);

      await cubit.submitEmergency(service: EmergencyService.all[0]);

      expect(cubit.state, isA<HomeError>());
      expect((cubit.state as HomeError).errorType, equals(HomeErrorType.server));
    });
  });

  group('Full Confirmation UI & Tracking Transition Flow', () {
    Widget createTestApp({required ApiClient apiClient, required AuthCubit authCubit}) {
      return MultiBlocProvider(
        providers: [
          BlocProvider<LocaleCubit>(create: (_) => LocaleCubit()),
          BlocProvider<AuthCubit>.value(value: authCubit),
          BlocProvider<HomeCubit>(create: (_) => HomeCubit(apiClient)),
          BlocProvider<TrackingCubit>(create: (_) => TrackingCubit(apiClient)),
        ],
        child: const MaterialApp(
          localizationsDelegates: [
            SirenLocalizations.delegate,
            GlobalMaterialLocalizations.delegate,
            GlobalWidgetsLocalizations.delegate,
            GlobalCupertinoLocalizations.delegate,
          ],
          supportedLocales: [Locale('ar'), Locale('en')],
          home: MainShell(enableSubmissionFlow: true),
        ),
      );
    }

    testWidgets('Submitting emergency from ConfirmationSheet transitions to Tracking only on authoritative success', (tester) async {
      final mockClient = MockHttpClient((req) async {
        if (req.url.path == '/api/v1/mobile/emergency-requests') {
          return http.Response(
            jsonEncode({
              'request_id': 'req-auth-live-4455',
              'incident_id': 'inc-live-11',
              'status': 'RECEIVED',
              'service': 'AMBULANCE',
              'received_at': '2026-09-09T12:00:00Z',
              'tracking_available': true,
            }),
            201,
            headers: {'content-type': 'application/json'},
          );
        }
        if (req.url.path.contains('/api/v1/mobile/emergency-requests/req-auth-live-4455')) {
          return http.Response(
            jsonEncode({
              'request_id': 'req-auth-live-4455',
              'incident_id': 'inc-live-11',
              'status': 'RECEIVED',
              'service': 'AMBULANCE',
              'eta_minutes': null,
              'updated_at': 'Just now',
            }),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('Not Found', 404);
      });

      final apiClient = ApiClient(client: mockClient, sessionCredential: 'token-abc');
      final authCubit = AuthCubit(apiClient);
      authCubit.emit(const Authenticated(testProfile));

      await tester.pumpWidget(createTestApp(apiClient: apiClient, authCubit: authCubit));
      await tester.pumpAndSettle();

      // Starts on Home
      expect(find.byType(HomeScreen), findsOneWidget);

      // Open ConfirmationSheet for Ambulance
      await tester.tap(find.byKey(const Key('service_card_ambulance')));
      await tester.pumpAndSettle();
      expect(find.byType(ConfirmationSheet), findsOneWidget);

      // Tap Confirm Emergency
      await tester.tap(find.byKey(const Key('confirm_sheet_submit_button')));
      await tester.pumpAndSettle();

      // Sheet is closed upon success
      expect(find.byType(ConfirmationSheet), findsNothing);

      // Authoritative request ID is persisted
      expect(await StorageService.getActiveRequestId(), equals('req-auth-live-4455'));

      // Automatically transitioned to Tracking screen (index 1)
      expect(find.byType(TrackingScreen), findsOneWidget);
    });

    testWidgets('Failed submission keeps sheet open, displays error, and allows retry without navigating to Tracking', (tester) async {
      int postAttempt = 0;
      final mockClient = MockHttpClient((req) async {
        if (req.method == 'POST') {
          postAttempt++;
          if (postAttempt == 1) {
            return http.Response('Internal Server Error', 500);
          }
          return http.Response(
            jsonEncode({
              'request_id': 'req-auth-retry-ok',
              'incident_id': 'inc-live-22',
              'status': 'RECEIVED',
              'service': 'FIRE',
              'received_at': '2026-09-09T12:00:00Z',
              'tracking_available': true,
            }),
            201,
            headers: {'content-type': 'application/json'},
          );
        }
        if (req.method == 'GET') {
          return http.Response(
            jsonEncode({
              'request_id': 'req-auth-retry-ok',
              'incident_id': 'inc-live-22',
              'status': 'RECEIVED',
              'service': 'FIRE',
              'updated_at': 'Just now',
            }),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('Not Found', 404);
      });

      final apiClient = ApiClient(client: mockClient);
      final authCubit = AuthCubit(apiClient);
      authCubit.emit(const Authenticated(testProfile));

      await tester.pumpWidget(createTestApp(apiClient: apiClient, authCubit: authCubit));
      await tester.pumpAndSettle();

      // Open sheet for Fire
      await tester.tap(find.byKey(const Key('service_card_fire')));
      await tester.pumpAndSettle();

      // Tap Confirm Emergency -> Server 500 failure
      await tester.tap(find.byKey(const Key('confirm_sheet_submit_button')));
      await tester.pumpAndSettle();

      // Sheet remains open!
      expect(find.byType(ConfirmationSheet), findsOneWidget);
      // Inline error banner is rendered
      expect(find.byKey(const Key('confirm_sheet_error_banner')), findsOneWidget);
      // Does NOT navigate to Tracking
      expect(find.byType(TrackingScreen), findsNothing);
      expect(await StorageService.getActiveRequestId(), isNull);

      // Tap Retry button on sheet
      await tester.tap(find.byKey(const Key('confirm_sheet_submit_button')));
      await tester.pumpAndSettle();

      // Authoritative success: sheet closes, transitions to Tracking
      expect(find.byType(ConfirmationSheet), findsNothing);
      expect(await StorageService.getActiveRequestId(), equals('req-auth-retry-ok'));
      expect(find.byType(TrackingScreen), findsOneWidget);
    });
  });
}
