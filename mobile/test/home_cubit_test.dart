import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator/geolocator.dart';
import 'package:sirengrid_citizen/core/api_client.dart';
import 'package:sirengrid_citizen/core/location.dart';
import 'package:sirengrid_citizen/core/storage.dart';
import 'package:sirengrid_citizen/features/emergency/emergency_service.dart';
import 'package:sirengrid_citizen/features/emergency/home_cubit.dart';

import 'support.dart';

void main() {
  setUp(() => SecureStore.useInMemory());
  tearDown(() => SecureStore.reset());

  HomeCubit build(ScriptedClient c, FakeLocationPort port) => HomeCubit(
    ApiClient(client: c, accessToken: 'tok'),
    LocationService(port),
  );

  test(
    'emergency body carries service + location only — never identity',
    () async {
      final c = ScriptedClient()
        ..enqueue(201, {'request_id': 'req-1', 'incident_id': 'inc-1'});
      final cubit = build(c, FakeLocationPort());

      await cubit.submit(EmergencyService.ambulance);

      final body = c.bodyOf(c.lastRequest);
      expect(body['service'], 'AMBULANCE');
      expect(body['location'], {'lat': 30.0561, 'lon': 31.3452});
      expect(body.containsKey('location_accuracy_m'), isTrue);
      expect(body['client_timestamp'], isA<String>());
      for (final forbidden in [
        'citizen_reference',
        'national_id',
        'phone',
        'name',
        'registered_address',
        'severity',
      ]) {
        expect(
          body.containsKey(forbidden),
          isFalse,
          reason: 'must not send $forbidden',
        );
      }
      expect(c.lastRequest.headers['Idempotency-Key'], isNotEmpty);
    },
  );

  test(
    '201 -> HomeSubmitted, clears the idempotency key, stores active id',
    () async {
      final c = ScriptedClient()
        ..enqueue(201, {'request_id': 'req-9', 'incident_id': 'inc-9'});
      final cubit = build(c, FakeLocationPort());
      await cubit.submit(EmergencyService.fire);
      expect(cubit.state, isA<HomeSubmitted>());
      expect((cubit.state as HomeSubmitted).requestId, 'req-9');
      expect(await SecureStore.readPendingIdempotencyKey(), isNull);
      expect(await SecureStore.readActiveRequestId(), 'req-9');
    },
  );

  test('200 idempotent replay is also a success', () async {
    final c = ScriptedClient()..enqueue(200, {'request_id': 'req-replay'});
    final cubit = build(c, FakeLocationPort());
    await cubit.submit(EmergencyService.ambulance);
    expect(cubit.state, isA<HomeSubmitted>());
  });

  test('409 conflict is surfaced and the spent key is dropped', () async {
    await SecureStore.savePendingIdempotencyKey('old-key');
    final c = ScriptedClient()
      ..enqueue(409, {
        'detail': {'code': 'IDEMPOTENCY_CONFLICT'},
      });
    final cubit = build(c, FakeLocationPort());
    await cubit.submit(EmergencyService.ambulance);
    expect(cubit.state, isA<HomeSubmitFailure>());
    expect((cubit.state as HomeSubmitFailure).kind, SubmitFailureKind.conflict);
    expect(await SecureStore.readPendingIdempotencyKey(), isNull);
  });

  test('422 (validation / current-location) is distinct from 409', () async {
    final c = ScriptedClient()
      ..enqueue(422, {
        'detail': {'code': 'CURRENT_LOCATION_REQUIRED'},
      });
    final cubit = build(c, FakeLocationPort());
    await cubit.submit(EmergencyService.ambulance);
    expect(
      (cubit.state as HomeSubmitFailure).kind,
      SubmitFailureKind.validation,
    );
  });

  test('network failure keeps the idempotency key for a safe retry', () async {
    final port = FakeLocationPort();
    final api = ApiClient(client: ThrowingClient(), accessToken: 'tok');
    final cubit = HomeCubit(api, LocationService(port));
    await cubit.submit(EmergencyService.ambulance);
    final fail = cubit.state as HomeSubmitFailure;
    expect(fail.kind, SubmitFailureKind.network);
    final key = await SecureStore.readPendingIdempotencyKey();
    expect(key, isNotNull);
    expect(fail.idempotencyKey, key);
  });

  test('retry reuses the persisted idempotency key', () async {
    await SecureStore.savePendingIdempotencyKey('sticky-key');
    final c = ScriptedClient()
      ..enqueue(500, {'detail': 'boom'})
      ..enqueue(201, {'request_id': 'req-ok'});
    final cubit = build(c, FakeLocationPort());
    await cubit.submit(EmergencyService.ambulance);
    expect(c.requests.first.headers['Idempotency-Key'], 'sticky-key');
    await cubit.retry();
    expect(c.requests.last.headers['Idempotency-Key'], 'sticky-key');
    expect(cubit.state, isA<HomeSubmitted>());
  });

  test(
    'a second submit while one is in flight is ignored (duplicate tap)',
    () async {
      final c = ScriptedClient()
        ..enqueue(201, {'request_id': 'req-a'})
        ..enqueue(201, {'request_id': 'req-b'});
      final cubit = build(c, FakeLocationPort());
      await Future.wait([
        cubit.submit(EmergencyService.ambulance),
        cubit.submit(EmergencyService.ambulance),
      ]);
      expect(c.requests, hasLength(1));
    },
  );

  test('location denied -> a location failure, no network call', () async {
    final port = FakeLocationPort(permission: LocationPermission.denied);
    final c = ScriptedClient();
    final cubit = build(c, port);
    await cubit.submit(EmergencyService.ambulance);
    final fail = cubit.state as HomeSubmitFailure;
    expect(fail.kind, SubmitFailureKind.location);
    expect(c.requests, isEmpty);
  });
}
