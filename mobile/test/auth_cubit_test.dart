import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:sirengrid_citizen/core/api_client.dart';
import 'package:sirengrid_citizen/core/storage.dart';
import 'package:sirengrid_citizen/features/auth/auth_cubit.dart';

import 'support.dart';

const _profileJson = {
  'citizen_reference': 'demo-citizen-001',
  'display_name': 'Mariam Adel',
  'phone': '01000000000',
  'registered_address': '12 Demo Street, Nasr City, Cairo',
  'national_id_masked': '**********1234',
  'identity_status': 'DEMO_VERIFIED',
};

void main() {
  setUp(() => SecureStore.useInMemory());
  tearDown(() => SecureStore.reset());

  AuthCubit build(ScriptedClient c, {List<CitizenRef>? hooks}) {
    final api = ApiClient(client: c);
    return AuthCubit(
      api,
      onAuthenticated: (_) async => hooks?.add(CitizenRef()),
    );
  }

  test(
    'login parses access_token, persists it, then loads the 6-field profile',
    () async {
      final c = ScriptedClient()
        ..enqueue(200, {
          'access_token': 'tok-123',
          'token_type': 'bearer',
        }, matchPathEndsWith: '/auth/login')
        ..enqueue(200, _profileJson, matchPathEndsWith: '/me');
      final hooks = <CitizenRef>[];
      final cubit = build(c, hooks: hooks);

      await cubit.login('01000000000', '1234');

      expect(cubit.state, isA<Authenticated>());
      final p = cubit.state.profile!;
      expect(p.citizenReference, 'demo-citizen-001');
      expect(p.displayName, 'Mariam Adel');
      expect(p.registeredAddress, contains('Nasr City'));
      expect(p.nationalIdMasked, '**********1234');
      expect(await SecureStore.readAccessToken(), 'tok-123');
      // login POST must carry only phone + pin
      final loginReq = c.requests.firstWhere(
        (r) => r.url.path.endsWith('/auth/login'),
      );
      expect(c.bodyOf(loginReq).keys, unorderedEquals(['phone', 'pin']));
      // after-auth hook fired (FCM registration binding)
      expect(hooks, hasLength(1));
    },
  );

  test(
    'a stale session_token-only response is rejected as a contract mismatch',
    () async {
      final c = ScriptedClient()
        ..enqueue(200, {
          'session_token': 'tok-123',
        }, matchPathEndsWith: '/auth/login');
      final cubit = build(c);
      await cubit.login('01000000000', '1234');
      expect(cubit.state, isA<AuthFailure>());
      expect((cubit.state as AuthFailure).loginFailure, isTrue);
    },
  );

  test(
    'invalid credentials -> AuthFailure(loginFailure) and no stored token',
    () async {
      final c = ScriptedClient()
        ..enqueue(401, {'detail': 'Invalid credentials'});
      final cubit = build(c);
      await cubit.login('01000000000', '9999');
      expect(cubit.state, isA<AuthFailure>());
      expect(await SecureStore.readAccessToken(), isNull);
    },
  );

  test(
    'PIN outside the supported 4-8 digit range is rejected client-side',
    () async {
      final c = ScriptedClient();
      final cubit = build(c);
      await cubit.login('01000000000', '12');
      expect(cubit.state, isA<AuthFailure>());
      expect(c.requests, isEmpty);
    },
  );

  test('a 6-digit registered PIN can be used to log in', () async {
    final c = ScriptedClient()
      ..enqueue(200, {
        'access_token': 'tok-123',
        'token_type': 'bearer',
      }, matchPathEndsWith: '/auth/login')
      ..enqueue(200, _profileJson, matchPathEndsWith: '/me');
    final cubit = build(c);

    await cubit.login('01000000000', '123456');

    expect(cubit.state, isA<Authenticated>());
    expect(c.bodyOf(c.requests.first)['pin'], '123456');
  });

  test('restoreSession validates the stored token via /me', () async {
    await SecureStore.saveAccessToken('tok-xyz');
    final c = ScriptedClient()
      ..enqueue(200, _profileJson, matchPathEndsWith: '/me');
    final cubit = build(c);
    await cubit.restoreSession();
    expect(cubit.state, isA<Authenticated>());
    expect(c.requests.single.headers['Authorization'], 'Bearer tok-xyz');
  });

  test('restore with a 401 clears the stored session', () async {
    await SecureStore.saveAccessToken('expired');
    final c = ScriptedClient()..enqueue(401, {'detail': 'expired'});
    final cubit = build(c);
    await cubit.restoreSession();
    expect(cubit.state, isA<Unauthenticated>());
    expect(await SecureStore.readAccessToken(), isNull);
  });

  test(
    'restore during a network outage keeps the token and reports the failure',
    () async {
      await SecureStore.saveAccessToken('tok-keep');
      final api = ApiClient(client: _ThrowingClient());
      final cubit = AuthCubit(api);
      await cubit.restoreSession();
      expect(cubit.state, isA<AuthFailure>());
      expect((cubit.state as AuthFailure).sessionCheckFailure, isTrue);
      expect(
        await SecureStore.readAccessToken(),
        'tok-keep',
      ); // not fabricated, not cleared
    },
  );

  test(
    'logout calls /auth/logout, runs the before-logout hook, clears session',
    () async {
      await SecureStore.saveAccessToken('tok-1');
      await SecureStore.saveActiveRequestId('req-1');
      final c = ScriptedClient()
        ..enqueue(204, '', matchPathEndsWith: '/auth/logout');
      var hookRan = false;
      final cubit = AuthCubit(
        ApiClient(client: c, accessToken: 'tok-1'),
        onBeforeLogout: () async => hookRan = true,
      );
      await cubit.logout();
      expect(hookRan, isTrue);
      expect(cubit.state, isA<Unauthenticated>());
      expect(await SecureStore.readAccessToken(), isNull);
      expect(await SecureStore.readActiveRequestId(), isNull);
    },
  );
}

class CitizenRef {}

class _ThrowingClient extends http.BaseClient {
  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) =>
      throw Exception('offline');
}
