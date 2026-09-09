import 'package:flutter_test/flutter_test.dart';
import 'package:sirengrid_citizen/core/api_client.dart';
import 'package:sirengrid_citizen/core/storage.dart';
import 'package:sirengrid_citizen/notifications/device_registrar.dart';
import 'package:sirengrid_citizen/notifications/messaging_port.dart';
import 'package:sirengrid_citizen/notifications/notification_coordinator.dart';

import 'support.dart';

void main() {
  setUp(() => SecureStore.useInMemory());
  tearDown(() => SecureStore.reset());

  ({NotificationCoordinator coord, ScriptedClient http, FakeMessagingPort msg})
  build() {
    final http = ScriptedClient();
    final msg = FakeMessagingPort();
    final coord = NotificationCoordinator(
      msg,
      DeviceRegistrar(ApiClient(client: http, accessToken: 'tok')),
    );
    return (coord: coord, http: http, msg: msg);
  }

  test(
    'bootstrap wires listeners and does NOT register a token pre-auth',
    () async {
      final b = build();
      await b.coord.bootstrap();
      // no /devices/register call before onAuthenticated
      expect(
        b.http.requests.where((r) => r.url.path.endsWith('/devices/register')),
        isEmpty,
      );
      await b.coord.close();
    },
  );

  test('onAuthenticated registers the FCM token with the backend', () async {
    final b = build();
    b.http.enqueue(200, {
      'registered': true,
    }, matchPathEndsWith: '/devices/register');
    await b.coord.bootstrap();
    await b.coord.onAuthenticated();
    final req = b.http.requests.firstWhere(
      (r) => r.url.path.endsWith('/devices/register'),
    );
    final body = b.http.bodyOf(req);
    expect(body['token'], 'fake-token-1');
    expect(body['platform'], anyOf('ANDROID', 'IOS'));
    // identity is never in the body
    expect(body.containsKey('citizen_reference'), isFalse);
    expect(
      await SecureStore.readPendingDeviceToken(),
      isNull,
    ); // cleared on success
    await b.coord.close();
  });

  test(
    'token obtained while unauthenticated is deferred, then flushed on auth',
    () async {
      final b = build();
      await b.coord.bootstrap();
      b.msg.emitRefresh('refreshed-token-A');
      await Future<void>.delayed(Duration.zero);
      // deferred: cached, not yet registered
      expect(await SecureStore.readPendingDeviceToken(), 'refreshed-token-A');
      expect(
        b.http.requests.where((r) => r.url.path.endsWith('/devices/register')),
        isEmpty,
      );

      b.http.enqueue(200, {
        'registered': true,
      }, matchPathEndsWith: '/devices/register');
      await b.coord.onAuthenticated();
      expect(
        b.http.requests.any((r) => r.url.path.endsWith('/devices/register')),
        isTrue,
      );
      await b.coord.close();
    },
  );

  test('token refresh while authenticated re-registers', () async {
    final b = build();
    b.http.enqueue(200, {
      'registered': true,
    }, matchPathEndsWith: '/devices/register');
    await b.coord.bootstrap();
    await b.coord.onAuthenticated();
    b.http.enqueue(200, {
      'registered': true,
    }, matchPathEndsWith: '/devices/register');
    b.msg.emitRefresh('rotated-token-B');
    await Future<void>.delayed(Duration.zero);
    final regs = b.http.requests
        .where((r) => r.url.path.endsWith('/devices/register'))
        .map((r) => b.http.bodyOf(r)['token'])
        .toList();
    expect(regs, contains('rotated-token-B'));
    await b.coord.close();
  });

  test(
    'a foreground push becomes a refetch intent (never treated as truth)',
    () async {
      final b = build();
      await b.coord.bootstrap();
      final got = <NotificationIntent>[];
      final sub = b.coord.intents.listen(got.add);
      b.msg.emitForeground(
        const PushMessage(
          data: {'type': 'RESPONSE_ASSIGNED', 'request_id': 'req-1'},
          title: 'Response assigned',
        ),
      );
      await Future<void>.delayed(Duration.zero);
      expect(got, hasLength(1));
      expect(got.single.type, 'RESPONSE_ASSIGNED');
      expect(got.single.requestId, 'req-1');
      expect(got.single.isRequestScoped, isTrue);
      expect(got.single.fromTap, isFalse);
      await sub.cancel();
      await b.coord.close();
    },
  );

  test(
    'a clear-the-way push is classified and carries no request id',
    () async {
      final b = build();
      await b.coord.bootstrap();
      final got = <NotificationIntent>[];
      final sub = b.coord.intents.listen(got.add);
      b.msg.emitOpened(
        const PushMessage(
          data: {'type': 'EMERGENCY_VEHICLE_APPROACHING', 'alert_id': 'a-9'},
        ),
      );
      await Future<void>.delayed(Duration.zero);
      expect(got.single.isClearTheWay, isTrue);
      expect(got.single.isRequestScoped, isFalse);
      expect(got.single.fromTap, isTrue);
      await sub.cancel();
      await b.coord.close();
    },
  );

  test('onLoggedOut best-effort unregisters the last token', () async {
    final b = build();
    b.http.enqueue(200, {
      'registered': true,
    }, matchPathEndsWith: '/devices/register');
    await b.coord.bootstrap();
    await b.coord.onAuthenticated();
    b.http.enqueue(200, {}, matchPathEndsWith: '/devices/unregister');
    await b.coord.onLoggedOut();
    expect(
      b.http.requests.any((r) => r.url.path.endsWith('/devices/unregister')),
      isTrue,
    );
    await b.coord.close();
  });

  test(
    'coordinator is inert (no throw) when Firebase config is absent',
    () async {
      final http = ScriptedClient();
      final msg = FakeMessagingPort(available: false);
      final coord = NotificationCoordinator(
        msg,
        DeviceRegistrar(ApiClient(client: http, accessToken: 'tok')),
      );
      await coord.bootstrap();
      await coord.onAuthenticated();
      await coord.requestPermission();
      expect(http.requests, isEmpty);
      await coord.close();
    },
  );
}
