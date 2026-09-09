import 'package:flutter_test/flutter_test.dart';
import 'package:sirengrid_citizen/core/api_client.dart';
import 'package:sirengrid_citizen/core/storage.dart';
import 'package:sirengrid_citizen/features/tracking/tracking_cubit.dart';
import 'package:sirengrid_citizen/features/tracking/tracking_models.dart';

import 'support.dart';

Map<String, dynamic> snap({
  String status = 'EN_ROUTE',
  Object? eta,
  Map<String, dynamic>? responder,
  Map<String, dynamic>? route,
  Map<String, dynamic>? emergencyLocation,
  bool trackingAvailable = true,
  Map<String, dynamic> extra = const {},
}) => {
  'request_id': 'req-1',
  'incident_id': 'inc-1',
  'service': 'AMBULANCE',
  'status': status,
  'eta_seconds': eta,
  'responder': responder,
  'emergency_location': emergencyLocation ?? {'lat': 30.05, 'lon': 31.34},
  'route': route,
  'last_updated': DateTime.now().toUtc().toIso8601String(),
  'tracking_available': trackingAvailable,
  ...extra,
};

const _responder = {
  'id': 'res-2',
  'label': 'Ambulance A2',
  'location': {'lat': 30.061, 'lon': 31.33},
  'last_updated': '2026-09-09T12:00:00Z',
  'freshness_status': 'FRESH',
  'data_reality': 'SIMULATED',
  'operational_status': 'EN_ROUTE',
};

const _route = {
  'geometry': {
    'type': 'LineString',
    'coordinates': [
      [31.33, 30.061],
      [31.335, 30.058],
      [31.34, 30.05],
    ],
  },
  'remaining_eta_seconds': 182.0,
  'progress_fraction': 0.35,
  'data_reality': 'SIMULATED',
  'tracking_source': 'SIMULATED_ROUTE_PROJECTION',
};

void main() {
  group('TrackingSnapshot parsing', () {
    test('integer ETA parses (float-safe)', () {
      final s = TrackingSnapshot.fromJson(snap(eta: 240));
      expect(s.etaSeconds, 240.0);
      expect(s.etaMinutes, 4);
    });

    test('decimal ETA parses without an unsafe cast', () {
      final s = TrackingSnapshot.fromJson(snap(eta: 179.6));
      expect(s.etaSeconds, closeTo(179.6, 0.001));
      expect(s.etaMinutes, 3);
    });

    test('tracking unavailable / no responder', () {
      final s = TrackingSnapshot.fromJson(
        snap(status: 'UNDER_REVIEW', trackingAvailable: false, responder: null),
      );
      expect(s.trackingAvailable, isFalse);
      expect(s.responder, isNull);
      expect(s.status, CitizenRequestStatus.underReview);
    });

    test(
      'assigned responder + route geometry + progress + operational status',
      () {
        final s = TrackingSnapshot.fromJson(
          snap(responder: _responder, route: _route, eta: 200),
        );
        expect(s.responder!.id, 'res-2');
        expect(s.responder!.operationalStatus, 'EN_ROUTE');
        expect(s.responder!.location!.latitude, 30.061);
        expect(s.route!.polyline, hasLength(3));
        expect(s.route!.progressFraction, closeTo(0.35, 0.001));
        // prefers the route's remaining ETA over the top-level eta_seconds
        expect(s.effectiveEtaSeconds, 182.0);
      },
    );

    test('SIMULATED provenance is detected truthfully', () {
      final s = TrackingSnapshot.fromJson(
        snap(responder: _responder, route: _route),
      );
      expect(s.isSimulated, isTrue);
      expect(s.route!.isSimulatedProjection, isTrue);
    });

    test(
      'malformed route geometry yields an empty polyline, never a crash',
      () {
        final bad = Map<String, dynamic>.from(_route)
          ..['geometry'] = {
            'type': 'LineString',
            'coordinates': [
              [31.33, 30.061],
              [999.0, 30.0],
            ],
          };
        final s = TrackingSnapshot.fromJson(
          snap(responder: _responder, route: bad),
        );
        expect(s.route!.polyline, isEmpty);
      },
    );

    test('unknown extra fields are ignored', () {
      final s = TrackingSnapshot.fromJson(
        snap(
          responder: _responder,
          extra: {
            'future_field': 42,
            'nested': {'x': 1},
          },
        ),
      );
      expect(s.requestId, 'req-1');
    });

    test('terminal COMPLETED status', () {
      final s = TrackingSnapshot.fromJson(snap(status: 'COMPLETED'));
      expect(s.status.isTerminal, isTrue);
      expect(s.status.timelineStep, 3);
    });
  });

  group('TrackingCubit', () {
    setUp(() => SecureStore.useInMemory());
    tearDown(() => SecureStore.reset());

    test('no active request -> idle', () async {
      final cubit = TrackingCubit(
        ApiClient(client: ScriptedClient(), accessToken: 't'),
      );
      await cubit.start();
      expect(cubit.state, isA<TrackingIdle>());
      await cubit.close();
    });

    test(
      'fetches, exposes the snapshot, then stops on a terminal state',
      () async {
        await SecureStore.saveActiveRequestId('req-1');
        final c = ScriptedClient()..enqueue(200, snap(status: 'COMPLETED'));
        final cubit = TrackingCubit(c.asApi());
        await cubit.start();
        expect(cubit.state, isA<TrackingReady>());
        expect(
          (cubit.state as TrackingReady).snapshot.status,
          CitizenRequestStatus.completed,
        );
        // terminal -> active request id cleared
        expect(await SecureStore.readActiveRequestId(), isNull);
        await cubit.close();
      },
    );

    test(
      'a transient error keeps the last snapshot and marks it degraded',
      () async {
        await SecureStore.saveActiveRequestId('req-1');
        final c = ScriptedClient()
          ..enqueue(200, snap(responder: _responder))
          ..enqueue(503, {'detail': 'unavailable'});
        final cubit = TrackingCubit(
          c.asApi(),
          pollInterval: const Duration(hours: 1),
        );
        await cubit.start();
        expect(cubit.state, isA<TrackingReady>());
        await cubit.refreshNow();
        final st = cubit.state as TrackingReady;
        expect(st.stalePolls, greaterThan(0));
        expect(st.snapshot.responder, isNotNull); // last good snapshot retained
        await cubit.close();
      },
    );

    test('404 is surfaced without clearing the stored id', () async {
      await SecureStore.saveActiveRequestId('req-1');
      final c = ScriptedClient()..enqueue(404, {'detail': 'not found'});
      final cubit = TrackingCubit(c.asApi());
      await cubit.start();
      expect(cubit.state, isA<TrackingUnavailable>());
      expect(await SecureStore.readActiveRequestId(), 'req-1');
      await cubit.close();
    });
  });
}

extension on ScriptedClient {
  ApiClient asApi() => ApiClient(client: this, accessToken: 'tok');
}
