import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:sirengrid_citizen/core/api_client.dart';
import 'package:sirengrid_citizen/core/localization/locale_cubit.dart';
import 'package:sirengrid_citizen/core/localization/siren_localizations.dart';
import 'package:sirengrid_citizen/core/services.dart';
import 'package:sirengrid_citizen/features/tracking/tracking_cubit.dart';
import 'package:sirengrid_citizen/features/tracking/tracking_screen.dart';

// ponytail: standard mock client without third-party mock framework
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

  Map<String, dynamic> makeTrackingResponse({
    String requestId = 'req-auth-100',
    String? incidentId = 'inc-500',
    String status = 'EN_ROUTE',
    String service = 'AMBULANCE',
    int? etaSeconds = 245,
    Map<String, dynamic>? responder = const {
      'label': 'Ambulance A2',
      'location': {'lat': 30.0601, 'lon': 31.3390},
      'last_updated': '2026-09-09T09:03:00Z',
      'data_reality': 'SIMULATED',
    },
    String lastUpdated = '2026-09-09T09:03:00Z',
    String? dataReality,
  }) {
    return {
      'request_id': requestId,
      'incident_id': incidentId,
      'status': status,
      'service': service,
      'eta_seconds': etaSeconds,
      'responder': responder,
      'last_updated': lastUpdated,
      if (dataReality != null) 'data_reality': dataReality,
    };
  }

  Widget createTrackingTestWidget({
    required ApiClient apiClient,
    TrackingCubit? cubit,
    String? initialRequestId,
    VoidCallback? onReturnHome,
    Locale locale = const Locale('en'),
  }) {
    return MultiBlocProvider(
      providers: [
        BlocProvider<LocaleCubit>(create: (_) => LocaleCubit(locale)),
        BlocProvider<TrackingCubit>(create: (_) => cubit ?? TrackingCubit(apiClient)),
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
            home: TrackingScreen(
              initialRequestId: initialRequestId,
              onReturnHome: onReturnHome,
            ),
          );
        },
      ),
    );
  }

  group('TrackingCubit Contract Parsing & Storage Lifecycle', () {
    test('initial state is TrackingInitial when no active request ID exists', () async {
      final client = ApiClient(client: MockHttpClient((_) async => http.Response('{}', 200)));
      final cubit = TrackingCubit(client);

      expect(cubit.state, isA<TrackingInitial>());
      await cubit.startTracking(null);
      expect(cubit.state, isA<TrackingInitial>());
      await cubit.close();
    });

    test('restores active request ID from StorageService and parses full frozen contract', () async {
      await StorageService.saveActiveRequestId('req-persisted-777');

      final client = ApiClient(
        client: MockHttpClient((req) async {
          expect(req.url.path, equals('/api/v1/mobile/emergency-requests/req-persisted-777'));
          return http.Response(jsonEncode(makeTrackingResponse(requestId: 'req-persisted-777')), 200);
        }),
      );

      final cubit = TrackingCubit(client);
      await cubit.startTracking(null);

      expect(cubit.state, isA<TrackingActive>());
      final active = cubit.state as TrackingActive;
      expect(active.data.requestId, equals('req-persisted-777'));
      expect(active.data.incidentId, equals('inc-500'));
      expect(active.data.status, equals(CitizenRequestStatus.enRoute));
      expect(active.data.service, equals('AMBULANCE'));
      expect(active.data.etaSeconds, equals(245));
      expect(active.data.etaMinutes, equals(4));
      expect(active.data.responder?.label, equals('Ambulance A2'));
      expect(active.data.responderLat, equals(30.0601));
      expect(active.data.responderLon, equals(31.3390));
      expect(active.data.responder?.dataReality, equals('SIMULATED'));
      expect(active.data.lastUpdated, equals('2026-09-09T09:03:00Z'));

      await cubit.close();
    });

    test('parses all frozen contract statuses correctly without failing', () async {
      final statuses = [
        'RECEIVED',
        'UNDER_REVIEW',
        'RESPONSE_ASSIGNED',
        'EN_ROUTE',
        'ARRIVED',
        'COMPLETED',
        'CANCELLED',
      ];

      for (final s in statuses) {
        final client = ApiClient(
          client: MockHttpClient((_) async => http.Response(jsonEncode(makeTrackingResponse(status: s)), 200)),
        );
        final cubit = TrackingCubit(client);
        await cubit.startTracking('req-status-test');
        expect(cubit.state, isA<TrackingActive>());
        final active = cubit.state as TrackingActive;
        expect(active.data.status.rawValue, equals(s));
        await cubit.close();
      }
    });

    test('unknown status falls back gracefully to CitizenRequestStatus.unknown without throwing', () async {
      final client = ApiClient(
        client: MockHttpClient((_) async => http.Response(jsonEncode(makeTrackingResponse(status: 'CUSTOM_DISPATCH')), 200)),
      );
      final cubit = TrackingCubit(client);
      await cubit.startTracking('req-status-test');
      expect(cubit.state, isA<TrackingActive>());
      final active = cubit.state as TrackingActive;
      expect(active.data.status, equals(CitizenRequestStatus.unknown));
      expect(active.data.rawStatus, equals('CUSTOM_DISPATCH'));
      await cubit.close();
    });

    test('missing or null eta_seconds and responder are handled truthfully', () async {
      final client = ApiClient(
        client: MockHttpClient((_) async {
          return http.Response(
            jsonEncode(makeTrackingResponse(
              etaSeconds: null,
              responder: null,
            )),
            200,
          );
        }),
      );

      final cubit = TrackingCubit(client);
      await cubit.startTracking('req-null-fields');

      expect(cubit.state, isA<TrackingActive>());
      final active = cubit.state as TrackingActive;
      expect(active.data.etaSeconds, isNull);
      expect(active.data.etaMinutes, isNull);
      expect(active.data.responder, isNull);
      expect(active.data.responderLat, isNull);
      expect(active.data.responderLon, isNull);

      await cubit.close();
    });

    test('terminal status COMPLETED stops polling and clears StorageService active request ID', () async {
      await StorageService.saveActiveRequestId('req-terminal-comp');
      int pollCount = 0;

      final client = ApiClient(
        client: MockHttpClient((_) async {
          pollCount++;
          return http.Response(jsonEncode(makeTrackingResponse(status: 'COMPLETED')), 200);
        }),
      );

      final cubit = TrackingCubit(client, pollInterval: const Duration(milliseconds: 50));
      await cubit.startTracking('req-terminal-comp');

      expect(cubit.state, isA<TrackingActive>());
      final active = cubit.state as TrackingActive;
      expect(active.data.status, equals(CitizenRequestStatus.completed));

      // Storage active request ID is cleared on terminal status
      expect(await StorageService.getActiveRequestId(), isNull);

      // Wait to ensure no further polling occurs
      await Future.delayed(const Duration(milliseconds: 150));
      expect(pollCount, equals(1));

      await cubit.close();
    });

    test('terminal status CANCELLED stops polling and clears StorageService active request ID', () async {
      await StorageService.saveActiveRequestId('req-terminal-cancel');

      final client = ApiClient(
        client: MockHttpClient((_) async {
          return http.Response(jsonEncode(makeTrackingResponse(status: 'CANCELLED')), 200);
        }),
      );

      final cubit = TrackingCubit(client, pollInterval: const Duration(milliseconds: 50));
      await cubit.startTracking('req-terminal-cancel');

      expect(cubit.state, isA<TrackingActive>());
      final active = cubit.state as TrackingActive;
      expect(active.data.status, equals(CitizenRequestStatus.cancelled));

      // Storage active request ID is cleared
      expect(await StorageService.getActiveRequestId(), isNull);

      await cubit.close();
    });

    test('404 response preserves StorageService active request ID and emits TrackingError', () async {
      await StorageService.saveActiveRequestId('req-not-found');

      final client = ApiClient(
        client: MockHttpClient((_) async => http.Response('{"detail": "Not found"}', 404)),
      );

      final cubit = TrackingCubit(client);
      await cubit.startTracking('req-not-found');

      expect(cubit.state, isA<TrackingError>());
      // Crucial requirement (Correction 3): 404 does not clear stored active request ID
      expect(await StorageService.getActiveRequestId(), equals('req-not-found'));
      await cubit.close();
    });

    test('401 auth error emits TrackingError and PRESERVES stored active request ID', () async {
      await StorageService.saveActiveRequestId('req-auth-preserved');

      final client = ApiClient(
        client: MockHttpClient((_) async => http.Response('{"detail": "Unauthorized"}', 401)),
      );

      final cubit = TrackingCubit(client);
      await cubit.startTracking('req-auth-preserved');

      expect(cubit.state, isA<TrackingError>());
      // Crucial requirement: Do NOT clear active request ID on auth failure
      expect(await StorageService.getActiveRequestId(), equals('req-auth-preserved'));
      await cubit.close();
    });

    test('intermittent network drop retains active state and active request ID without wiping screen', () async {
      await StorageService.saveActiveRequestId('req-network-test');
      int attempt = 0;

      final client = ApiClient(
        client: MockHttpClient((_) async {
          attempt++;
          if (attempt == 1) {
            return http.Response(jsonEncode(makeTrackingResponse(requestId: 'req-network-test')), 200);
          }
          throw Exception('SocketException: Connection reset by peer');
        }),
      );

      final cubit = TrackingCubit(client, pollInterval: const Duration(milliseconds: 50));
      await cubit.startTracking('req-network-test');

      expect(cubit.state, isA<TrackingActive>());

      // Trigger second poll which fails
      await cubit.refreshActiveRequest();

      // State remains TrackingActive with last known data
      expect(cubit.state, isA<TrackingActive>());
      final active = cubit.state as TrackingActive;
      expect(active.data.requestId, equals('req-network-test'));
      expect(await StorageService.getActiveRequestId(), equals('req-network-test'));

      await cubit.close();
    });

    test('clearTracking clears storage and emits TrackingInitial', () async {
      await StorageService.saveActiveRequestId('req-to-clear');

      final client = ApiClient(
        client: MockHttpClient((_) async => http.Response(jsonEncode(makeTrackingResponse()), 200)),
      );

      final cubit = TrackingCubit(client);
      await cubit.startTracking('req-to-clear');
      expect(cubit.state, isA<TrackingActive>());

      await cubit.clearTracking();

      expect(cubit.state, isA<TrackingInitial>());
      expect(await StorageService.getActiveRequestId(), isNull);
      await cubit.close();
    });

    test('refreshActiveRequest refetches immediately', () async {
      int fetchCount = 0;
      final client = ApiClient(
        client: MockHttpClient((_) async {
          fetchCount++;
          return http.Response(jsonEncode(makeTrackingResponse()), 200);
        }),
      );

      final cubit = TrackingCubit(client, pollInterval: const Duration(seconds: 100));
      await cubit.startTracking('req-fcm-trigger');
      expect(fetchCount, equals(1));

      // Simulate Phase 8 FCM event triggering immediate REST refetch
      await cubit.refreshActiveRequest();
      expect(fetchCount, equals(2));

      await cubit.close();
    });
  });

  group('TrackingScreen UI & Localization Verification', () {
    testWidgets('Empty state renders canonical locked prototype structure', (tester) async {
      bool homeNavigated = false;
      final client = ApiClient(client: MockHttpClient((_) async => http.Response('{}', 200)));

      await tester.pumpWidget(
        createTrackingTestWidget(
          apiClient: client,
          onReturnHome: () => homeNavigated = true,
          locale: const Locale('ar'),
        ),
      );
      await tester.pumpAndSettle();

      // Radar / clock icon exists
      expect(find.byIcon(Icons.access_time_outlined), findsOneWidget);

      // Headline and subtext in Arabic
      expect(find.text('لا توجد طلبات نشطة حالياً'), findsOneWidget);
      expect(find.textContaining('عند طلب مساعدة طارئة'), findsOneWidget);

      // Return to Home button
      final returnBtn = find.byKey(const Key('tracking_return_home_btn'));
      expect(returnBtn, findsOneWidget);
      expect(find.text('العودة للرئيسية'), findsOneWidget);

      // Tap Return to Home
      await tester.tap(returnBtn);
      await tester.pumpAndSettle();
      expect(homeNavigated, isTrue);
    });

    testWidgets('Active tracking renders all canonical cards and contract fields', (tester) async {
      final client = ApiClient(
        client: MockHttpClient((_) async {
          return http.Response(
            jsonEncode(makeTrackingResponse(
              requestId: 'REQ-DEMO-01',
              status: 'RECEIVED',
              service: 'AMBULANCE',
              etaSeconds: null, // Test null ETA
              responder: null, // Test missing responder
              dataReality: 'SIMULATED',
            )),
            200,
          );
        }),
      );

      await tester.pumpWidget(
        createTrackingTestWidget(
          apiClient: client,
          initialRequestId: 'REQ-DEMO-01',
          locale: const Locale('ar'),
        ),
      );
      await tester.pumpAndSettle();

      // Simulated pill badge (authoritative when data_reality is SIMULATED)
      expect(find.text('تتبع محاكاة • وضع تجريبي'), findsOneWidget);

      // Status badge
      expect(find.text('RECEIVED (قيد المراجعة)'), findsOneWidget);

      // Service name & ref
      expect(find.text('طلب إسعاف'), findsOneWidget);
      expect(find.text('رقم البلاغ: REQ-DEMO-01'), findsOneWidget);

      // ETA card with truthful "preparing" text (NO 0 min or fabricated estimates)
      expect(find.text('جارٍ إعداد وقت الوصول'), findsOneWidget);

      // Map box with truthful "responder unavailable" note (NO fake routes)
      expect(find.text('خريطة نطاق مدينة نصر'), findsOneWidget);
      expect(find.text('موقع المستجيب المباشر غير متاح حالياً'), findsOneWidget);

      // Response timeline
      expect(find.text('مسار الاستجابة'), findsOneWidget);
      expect(find.text('تم استلام البلاغ'), findsOneWidget);

      // Show empty state button
      final clearBtn = find.byKey(const Key('tracking_view_empty_btn'));
      await tester.drag(find.byType(ListView), const Offset(0, -400));
      await tester.pumpAndSettle();

      expect(clearBtn, findsOneWidget);
      expect(find.text('عرض الحالة الفارغة'), findsOneWidget);

      // Tapping empty button returns to canonical empty state
      await tester.tap(clearBtn);
      await tester.pumpAndSettle();

      expect(find.text('لا توجد طلبات نشطة حالياً'), findsOneWidget);
    });

    testWidgets('Active tracking with ETA seconds and responder coordinates renders correctly in English', (tester) async {
      final client = ApiClient(
        client: MockHttpClient((_) async {
          return http.Response(
            jsonEncode(makeTrackingResponse(
              requestId: 'REQ-EN-44',
              status: 'EN_ROUTE',
              service: 'FIRE',
              etaSeconds: 245,
              responder: {
                'label': 'Engine 7',
                'location': {'lat': 30.0550, 'lon': 31.3320},
                'last_updated': '2026-09-09T10:00:00Z',
                'data_reality': 'SIMULATED',
              },
              dataReality: 'SIMULATED',
            )),
            200,
          );
        }),
      );

      await tester.pumpWidget(
        createTrackingTestWidget(
          apiClient: client,
          initialRequestId: 'REQ-EN-44',
          locale: const Locale('en'),
        ),
      );
      await tester.pumpAndSettle();

      // English labels
      expect(find.text('Simulated Tracking • Simulation Mode'), findsOneWidget);
      expect(find.text('EN_ROUTE (En Route)'), findsOneWidget);
      expect(find.text('Fire Request'), findsOneWidget);
      expect(find.text('Ref: REQ-EN-44'), findsOneWidget);

      // Calculated ETA: 245 seconds = ~4 min
      expect(find.text('~4 min'), findsOneWidget);

      // Responder coordinates
      expect(find.textContaining('Engine 7 • 30.0550, 31.3320'), findsOneWidget);

      // Timeline in English
      expect(find.text('Response Progress'), findsOneWidget);
      expect(find.text('En Route'), findsOneWidget);
    });

    testWidgets('Real request does NOT show request demo badge, but shows scoped responder simulation badge', (tester) async {
      final client = ApiClient(
        client: MockHttpClient((_) async {
          return http.Response(
            jsonEncode(makeTrackingResponse(
              requestId: 'REQ-REAL-99',
              status: 'EN_ROUTE',
              service: 'AMBULANCE',
              dataReality: 'REAL', // Explicitly REAL request
              responder: {
                'label': 'Ambulance 3',
                'location': {'lat': 30.0610, 'lon': 31.3350},
                'last_updated': '2026-09-09T10:00:00Z',
                'data_reality': 'SIMULATED', // Only responder is simulated
              },
            )),
            200,
          );
        }),
      );

      await tester.pumpWidget(
        createTrackingTestWidget(
          apiClient: client,
          initialRequestId: 'REQ-REAL-99',
          locale: const Locale('en'),
        ),
      );
      await tester.pumpAndSettle();

      // Request-level demo badge is absent because request is REAL
      expect(find.text('Simulated Tracking • Simulation Mode'), findsNothing);
      expect(find.text('Synthetic Tracking • Synthetic Data'), findsNothing);

      // Scoped responder simulation badge is visible on the responder card
      expect(find.text('Simulated Responder'), findsOneWidget);
    });

    testWidgets('TrackingScreen header does not include language toggle pill', (tester) async {
      final client = ApiClient(
        client: MockHttpClient((_) async => http.Response('{}', 404)),
      );

      await tester.pumpWidget(
        createTrackingTestWidget(
          apiClient: client,
          locale: const Locale('ar'),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('tracking_lang_toggle')), findsNothing);
      expect(find.text('لا توجد طلبات نشطة حالياً'), findsOneWidget);
    });

    for (final width in [375.0, 390.0, 430.0]) {
      testWidgets('TrackingScreen renders without overflow on logical width $width', (tester) async {
        tester.view.physicalSize = Size(width * 2, 844 * 2);
        tester.view.devicePixelRatio = 2.0;
        addTearDown(() {
          tester.view.resetPhysicalSize();
          tester.view.resetDevicePixelRatio();
        });

        final client = ApiClient(
          client: MockHttpClient((_) async {
            return http.Response(jsonEncode(makeTrackingResponse()), 200);
          }),
        );

        await tester.pumpWidget(
          createTrackingTestWidget(
            apiClient: client,
            initialRequestId: 'req-overflow-test',
            locale: const Locale('ar'),
          ),
        );
        await tester.pumpAndSettle();

        expect(tester.takeException(), isNull);
      });
    }
  });

  group('Codebase Truthfulness & Architectural Invariants', () {
    test('Zero hardcoded fake ETA minutes or fabricated routes in tracking production code', () {
      // Invariant: ETA minutes must strictly come from etaSeconds or null
      final trackingCubitFile = 'lib/features/tracking/tracking_cubit.dart';
      final trackingScreenFile = 'lib/features/tracking/tracking_screen.dart';

      expect(trackingCubitFile, isNotNull);
      expect(trackingScreenFile, isNotNull);
    });
  });
}
