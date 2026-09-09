import 'dart:async';
import 'dart:convert';

import 'package:geolocator/geolocator.dart';
import 'package:http/http.dart' as http;
import 'package:mocktail/mocktail.dart';
import 'package:sirengrid_citizen/core/location.dart';
import 'package:sirengrid_citizen/notifications/messaging_port.dart';

class MockHttpClient extends Mock implements http.Client {}

class FakeUri extends Fake implements Uri {}

void registerFallbacks() {
  registerFallbackValue(FakeUri());
  registerFallbackValue(<String, String>{});
}

/// Records requests and replies from a scripted queue (per method+path suffix).
class ScriptedClient extends http.BaseClient {
  ScriptedClient();

  final List<http.Request> requests = [];
  final List<_Reply> _script = [];

  void enqueue(int status, Object? body, {String? matchPathEndsWith}) {
    _script.add(
      _Reply(
        status,
        body is String ? body : jsonEncode(body ?? ''),
        matchPathEndsWith,
      ),
    );
  }

  http.Request get lastRequest => requests.last;

  Map<String, dynamic> bodyOf(http.Request r) =>
      r.body.isEmpty ? {} : jsonDecode(r.body) as Map<String, dynamic>;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final req = request as http.Request;
    requests.add(req);
    final idx = _script.indexWhere(
      (r) =>
          r.matchPathEndsWith == null ||
          request.url.path.endsWith(r.matchPathEndsWith!),
    );
    final reply = idx >= 0 ? _script.removeAt(idx) : _Reply(200, '{}', null);
    return http.StreamedResponse(
      Stream.value(utf8.encode(reply.body)),
      reply.status,
      request: request,
      headers: {'content-type': 'application/json'},
    );
  }
}

class _Reply {
  _Reply(this.status, this.body, this.matchPathEndsWith);
  final int status;
  final String body;
  final String? matchPathEndsWith;
}

/// Every request fails at the transport layer (simulates offline / DNS error).
class ThrowingClient extends http.BaseClient {
  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) =>
      throw Exception('transport failure');
}

/// Deterministic location seam for cubit tests.
class FakeLocationPort implements LocationPort {
  FakeLocationPort({
    this.serviceEnabled = true,
    this.permission = LocationPermission.always,
    this.position,
    this.throwOnCurrent,
  });

  bool serviceEnabled;
  LocationPermission permission;
  Position? position;
  Object? throwOnCurrent;

  @override
  Future<bool> isServiceEnabled() async => serviceEnabled;

  @override
  Future<LocationPermission> checkPermission() async => permission;

  @override
  Future<LocationPermission> requestPermission() async => permission;

  @override
  Future<Position> currentPosition({
    Duration timeLimit = const Duration(seconds: 12),
  }) async {
    if (throwOnCurrent != null) throw throwOnCurrent!;
    return position ??
        Position(
          latitude: 30.0561,
          longitude: 31.3452,
          timestamp: DateTime.now(),
          accuracy: 8,
          altitude: 0,
          altitudeAccuracy: 0,
          heading: 0,
          headingAccuracy: 0,
          speed: 0,
          speedAccuracy: 0,
        );
  }

  @override
  Future<bool> openAppSettings() async => true;

  @override
  Future<bool> openLocationSettings() async => true;
}

/// In-memory MessagingPort for FCM coordinator tests.
class FakeMessagingPort implements MessagingPort {
  FakeMessagingPort({this.available = true, this.token = 'fake-token-1'});

  bool available;
  String? token;
  PushPermission permission = PushPermission.authorized;
  int getTokenCalls = 0;

  final _refresh = StreamController<String>.broadcast();
  final _foreground = StreamController<PushMessage>.broadcast();
  final _opened = StreamController<PushMessage>.broadcast();
  PushMessage? initial;

  void emitRefresh(String t) => _refresh.add(t);
  void emitForeground(PushMessage m) => _foreground.add(m);
  void emitOpened(PushMessage m) => _opened.add(m);

  @override
  Future<bool> initialize() async => available;

  @override
  bool get isAvailable => available;

  @override
  Future<PushPermission> currentPermission() async => permission;

  @override
  Future<PushPermission> requestPermission() async => permission;

  @override
  Future<String?> getToken() async {
    getTokenCalls++;
    return token;
  }

  @override
  Stream<String> get onTokenRefresh => _refresh.stream;

  @override
  Stream<PushMessage> get onForegroundMessage => _foreground.stream;

  @override
  Stream<PushMessage> get onMessageOpenedApp => _opened.stream;

  @override
  Future<PushMessage?> getInitialMessage() async => initial;
}
