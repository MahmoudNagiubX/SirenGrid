import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:sirengrid_citizen/core/api_client.dart';
import 'package:sirengrid_citizen/core/services.dart';
import 'package:sirengrid_citizen/features/auth/auth_cubit.dart';

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
  setUp(() {
    StorageService.enableMockStorage();
  });

  tearDown(() {
    StorageService.resetStorage();
  });

  group('ApiClient header & credential rules', () {
    test('does not send Authorization header when no session credential is set', () {
      final client = ApiClient();
      final headers = client.buildHeaders();

      expect(headers.containsKey('Authorization'), isFalse);
      expect(headers['Authorization'], isNull);
      expect(client.hasSessionCredential, isFalse);
    });

    test('attaches Authorization Bearer header only when credential exists', () {
      final client = ApiClient(sessionCredential: 'test-token-12345');
      final headers = client.buildHeaders();

      expect(headers['Authorization'], equals('Bearer test-token-12345'));
      expect(client.hasSessionCredential, isTrue);

      client.clearSessionCredential();
      final headersAfterClear = client.buildHeaders();
      expect(headersAfterClear.containsKey('Authorization'), isFalse);
      expect(client.hasSessionCredential, isFalse);
    });
  });

  group('StorageService session persistence', () {
    test('persists, reads, and clears session credentials', () async {
      expect(await StorageService.hasSessionCredential(), isFalse);
      expect(await StorageService.getSessionCredential(), isNull);

      await StorageService.saveSessionCredential('sirengrid-auth-session-xyz');
      expect(await StorageService.hasSessionCredential(), isTrue);
      expect(await StorageService.getSessionCredential(), equals('sirengrid-auth-session-xyz'));

      await StorageService.clearSessionCredential();
      expect(await StorageService.hasSessionCredential(), isFalse);
      expect(await StorageService.getSessionCredential(), isNull);
    });
  });

  group('AuthCubit session restore', () {
    test('session restore with no stored session emits Unauthenticated', () async {
      final client = ApiClient();
      final cubit = AuthCubit(client);

      final states = <AuthState>[];
      final sub = cubit.stream.listen(states.add);

      await cubit.checkSession();
      await Future<void>.delayed(Duration.zero);

      expect(states.length, equals(2));
      expect(states[0], isA<AuthCheckingSession>());
      expect(states[1], isA<Unauthenticated>());
      expect(client.hasSessionCredential, isFalse);

      await sub.cancel();
      await cubit.close();
    });

    test('session restore with valid stored credential restores Authenticated profile', () async {
      await StorageService.saveSessionCredential('valid-persisted-token');

      final mockHttp = MockHttpClient((request) async {
        if (request.url.path == '/api/v1/mobile/me') {
          expect(request.headers['Authorization'], equals('Bearer valid-persisted-token'));
          return http.Response(
            jsonEncode({
              'citizen_reference': 'cit-101',
              'display_name': 'Ahmed Mansour',
              'phone': '+201001234567',
              'national_id_last4': '4821',
              'identity_status': 'Verified',
              'data_reality': 'SYNTHETIC',
            }),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('Not Found', 404);
      });

      final client = ApiClient(client: mockHttp);
      final cubit = AuthCubit(client);

      final states = <AuthState>[];
      final sub = cubit.stream.listen(states.add);

      await cubit.checkSession();
      await Future<void>.delayed(Duration.zero);

      expect(states.length, equals(2));
      expect(states[0], isA<AuthCheckingSession>());
      expect(states[1], isA<Authenticated>());

      final authState = states[1] as Authenticated;
      expect(authState.profile.displayName, equals('Ahmed Mansour'));
      expect(authState.profile.phone, equals('+201001234567'));
      expect(authState.profile.maskedNationalId, contains('4821'));
      expect(authState.profile.status, equals('Verified'));
      expect(client.sessionCredential, equals('valid-persisted-token'));

      await sub.cancel();
      await cubit.close();
    });

    test('session restore with expired credential (401) clears storage and emits Unauthenticated', () async {
      await StorageService.saveSessionCredential('expired-token-999');

      final mockHttp = MockHttpClient((request) async {
        if (request.url.path == '/api/v1/mobile/me') {
          return http.Response(jsonEncode({'detail': 'Session expired'}), 401);
        }
        return http.Response('Not Found', 404);
      });

      final client = ApiClient(client: mockHttp);
      final cubit = AuthCubit(client);

      final states = <AuthState>[];
      final sub = cubit.stream.listen(states.add);

      await cubit.checkSession();
      await Future<void>.delayed(Duration.zero);

      expect(states.length, equals(2));
      expect(states[0], isA<AuthCheckingSession>());
      expect(states[1], isA<Unauthenticated>());

      // Secure storage must be cleared
      expect(await StorageService.getSessionCredential(), isNull);
      expect(client.hasSessionCredential, isFalse);

      await sub.cancel();
      await cubit.close();
    });
  });

  group('AuthCubit login flow', () {
    test('login success: persists credential, sets client header, and emits Authenticated', () async {
      final mockHttp = MockHttpClient((request) async {
        if (request.url.path == '/api/v1/mobile/auth/login') {
          return http.Response(
            jsonEncode({'session_token': 'auth-token-citizen-01'}),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        if (request.url.path == '/api/v1/mobile/me') {
          expect(request.headers['Authorization'], equals('Bearer auth-token-citizen-01'));
          return http.Response(
            jsonEncode({
              'citizen_reference': 'cit-001',
              'display_name': 'Fatima El-Sayed',
              'phone': '+201099887766',
              'national_id_last4': '9876',
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
      final cubit = AuthCubit(client);

      final states = <AuthState>[];
      final sub = cubit.stream.listen(states.add);

      await cubit.loginWithPhoneAndPin('+201099887766', '1234');
      await Future<void>.delayed(Duration.zero);

      expect(states.length, equals(2));
      expect(states[0], isA<Authenticating>());
      expect(states[1], isA<Authenticated>());

      final authState = states[1] as Authenticated;
      expect(authState.profile.displayName, equals('Fatima El-Sayed'));
      expect(await StorageService.getSessionCredential(), equals('auth-token-citizen-01'));
      expect(client.sessionCredential, equals('auth-token-citizen-01'));

      await sub.cancel();
      await cubit.close();
    });

    test('login contract mismatch: missing session_token rejects with AuthFailure', () async {
      final mockHttp = MockHttpClient((request) async {
        if (request.url.path == '/api/v1/mobile/auth/login') {
          // Returns speculative alias 'token' instead of confirmed 'session_token'
          return http.Response(
            jsonEncode({'token': 'speculative-token-alias'}),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('Not Found', 404);
      });

      final client = ApiClient(client: mockHttp);
      final cubit = AuthCubit(client);

      final states = <AuthState>[];
      final sub = cubit.stream.listen(states.add);

      await cubit.loginWithPhoneAndPin('+201099887766', '1234');
      await Future<void>.delayed(Duration.zero);

      expect(states.length, equals(2));
      expect(states[0], isA<Authenticating>());
      expect(states[1], isA<AuthFailure>());

      final failure = states[1] as AuthFailure;
      expect(failure.message, contains('session_token'));
      expect(await StorageService.getSessionCredential(), isNull);

      await sub.cancel();
      await cubit.close();
    });

    test('profile contract mismatch: speculative alias in /mobile/me rejects with AuthFailure', () async {
      await StorageService.saveSessionCredential('stored-token');

      final mockHttp = MockHttpClient((request) async {
        if (request.url.path == '/api/v1/mobile/me') {
          // Speculative alias 'full_name' instead of 'display_name'
          return http.Response(
            jsonEncode({
              'citizen_reference': 'cit-001',
              'full_name': 'Fatima El-Sayed',
              'phone': '+201099887766',
              'national_id_last4': '9876',
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
      final cubit = AuthCubit(client);

      final states = <AuthState>[];
      final sub = cubit.stream.listen(states.add);

      await cubit.checkSession();
      await Future<void>.delayed(Duration.zero);

      expect(states.length, equals(2));
      expect(states[0], isA<AuthCheckingSession>());
      expect(states[1], isA<AuthFailure>());

      final failure = states[1] as AuthFailure;
      expect(failure.message, contains('Contract mismatch'));

      await sub.cancel();
      await cubit.close();
    });

    test('session check connectivity failure preserves stored session for retry', () async {
      await StorageService.saveSessionCredential('persistent-offline-token');

      final mockHttp = MockHttpClient((request) async {
        throw const SocketException('Temporary network connectivity failure');
      });

      final client = ApiClient(client: mockHttp);
      final cubit = AuthCubit(client);

      final states = <AuthState>[];
      final sub = cubit.stream.listen(states.add);

      await cubit.checkSession();
      await Future<void>.delayed(Duration.zero);

      expect(states.length, equals(2));
      expect(states[0], isA<AuthCheckingSession>());
      expect(states[1], isA<AuthFailure>());

      final failure = states[1] as AuthFailure;
      expect(failure.isSessionCheckFailure, isTrue);
      // Stored session must NOT be destroyed on temporary network error
      expect(await StorageService.getSessionCredential(), equals('persistent-offline-token'));

      await sub.cancel();
      await cubit.close();
    });

    test('login rejected (401): emits AuthFailure, does not persist credential', () async {
      final mockHttp = MockHttpClient((request) async {
        if (request.url.path == '/api/v1/mobile/auth/login') {
          return http.Response(jsonEncode({'detail': 'Invalid credentials'}), 401);
        }
        return http.Response('Not Found', 404);
      });

      final client = ApiClient(client: mockHttp);
      final cubit = AuthCubit(client);

      final states = <AuthState>[];
      final sub = cubit.stream.listen(states.add);

      await cubit.loginWithPhoneAndPin('+201099887766', '9999');
      await Future<void>.delayed(Duration.zero);

      expect(states.length, equals(2));
      expect(states[0], isA<Authenticating>());
      expect(states[1], isA<AuthFailure>());

      final failure = states[1] as AuthFailure;
      expect(failure.message, contains('Invalid credentials'));
      expect(await StorageService.getSessionCredential(), isNull);
      expect(client.hasSessionCredential, isFalse);

      await sub.cancel();
      await cubit.close();
    });

    test('login non-4-digit PIN rejects before server request', () async {
      final client = ApiClient();
      final cubit = AuthCubit(client);

      final states = <AuthState>[];
      final sub = cubit.stream.listen(states.add);

      await cubit.loginWithPhoneAndPin('+201099887766', '12'); // Only 2 digits
      await Future<void>.delayed(Duration.zero);

      expect(states.length, equals(1));
      expect(states[0], isA<AuthFailure>());

      final failure = states[0] as AuthFailure;
      expect(failure.message, contains('PIN must be exactly 4 digits'));

      await sub.cancel();
      await cubit.close();
    });

    test('network failure during login: emits explicit AuthFailure, no synthetic user fallback', () async {
      final mockHttp = MockHttpClient((request) async {
        throw const SocketException('Connection refused to FastAPI backend');
      });

      final client = ApiClient(client: mockHttp);
      final cubit = AuthCubit(client);

      final states = <AuthState>[];
      final sub = cubit.stream.listen(states.add);

      await cubit.loginWithPhoneAndPin('+201099887766', '1234');
      await Future<void>.delayed(Duration.zero);

      expect(states.length, equals(2));
      expect(states[0], isA<Authenticating>());
      expect(states[1], isA<AuthFailure>());

      final failure = states[1] as AuthFailure;
      expect(failure.message, contains('Connection error'));
      expect(await StorageService.getSessionCredential(), isNull);

      await sub.cancel();
      await cubit.close();
    });
  });

  group('AuthCubit logout flow', () {
    test('logout calls backend, clears secure storage, and emits Unauthenticated', () async {
      await StorageService.saveSessionCredential('session-to-logout');
      bool logoutEndpointCalled = false;

      final mockHttp = MockHttpClient((request) async {
        if (request.url.path == '/api/v1/mobile/auth/logout') {
          logoutEndpointCalled = true;
          expect(request.headers['Authorization'], equals('Bearer session-to-logout'));
          return http.Response(jsonEncode({'status': 'logged_out'}), 200);
        }
        return http.Response('Not Found', 404);
      });

      final client = ApiClient(client: mockHttp, sessionCredential: 'session-to-logout');
      final cubit = AuthCubit(client);

      final states = <AuthState>[];
      final sub = cubit.stream.listen(states.add);

      await cubit.logout();
      await Future<void>.delayed(Duration.zero);

      expect(logoutEndpointCalled, isTrue);
      expect(states.length, equals(1));
      expect(states[0], isA<Unauthenticated>());
      expect(await StorageService.getSessionCredential(), isNull);
      expect(client.hasSessionCredential, isFalse);

      await sub.cancel();
      await cubit.close();
    });

    test('offline logout clears local session even if remote revocation fails', () async {
      await StorageService.saveSessionCredential('offline-session-token');

      final mockHttp = MockHttpClient((request) async {
        throw const SocketException('No internet connection');
      });

      final client = ApiClient(client: mockHttp, sessionCredential: 'offline-session-token');
      final cubit = AuthCubit(client);

      final states = <AuthState>[];
      final sub = cubit.stream.listen(states.add);

      final remoteSuccess = await cubit.logout();
      await Future<void>.delayed(Duration.zero);

      expect(remoteSuccess, isFalse);
      expect(states.length, equals(1));
      expect(states[0], isA<Unauthenticated>());
      expect(await StorageService.getSessionCredential(), isNull);
      expect(client.hasSessionCredential, isFalse);

      await sub.cancel();
      await cubit.close();
    });
  });

  group('Codebase verification', () {
    test('guarantees no FirebaseAuth references in lib/', () {
      final libDir = Directory('lib');
      final dartFiles = libDir.listSync(recursive: true).whereType<File>().where((f) => f.path.endsWith('.dart'));

      for (final file in dartFiles) {
        final content = file.readAsStringSync();
        expect(content.contains('firebase_auth'), isFalse,
            reason: 'Found firebase_auth import/usage in ${file.path}');
        expect(content.contains('FirebaseAuth'), isFalse,
            reason: 'Found FirebaseAuth symbol in ${file.path}');
      }
    });
  });
}
