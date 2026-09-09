import 'dart:async';
import 'dart:developer' as dev;

import 'package:flutter_bloc/flutter_bloc.dart';

import '../core/storage.dart';
import 'device_registrar.dart';
import 'messaging_port.dart';

enum NotificationPermissionState { unknown, authorized, provisional, denied }

/// What a received / tapped notification wants the app to do. Push is never
/// truth — every intent resolves to "refetch the backend" (addendum §14/§19).
class NotificationIntent {
  const NotificationIntent({
    required this.type,
    this.requestId,
    this.alertId,
    this.title,
    this.body,
    this.fromTap = false,
  });
  final String type;
  final String? requestId;
  final String? alertId;
  final String? title;
  final String? body;
  final bool fromTap;

  bool get isRequestScoped => requestId != null && requestId!.isNotEmpty;
  bool get isClearTheWay =>
      type == 'CLEAR_THE_WAY' || type == 'EMERGENCY_VEHICLE_APPROACHING';
}

/// One focused coordinator for the whole FCM client lifecycle (addendum §18):
/// init → permission → token → refresh → foreground → tap → cold-start, plus
/// auth-bound device registration timing (§17). No notification business logic
/// lives in screens.
class NotificationCoordinator extends Cubit<NotificationPermissionState> {
  NotificationCoordinator(this._messaging, this._registrar)
    : super(NotificationPermissionState.unknown);

  final MessagingPort _messaging;
  final DeviceRegistrar _registrar;

  final _intents = StreamController<NotificationIntent>.broadcast();

  /// Screens listen here (Home shows Clear-the-Way; the app navigates to Track
  /// for request-scoped intents; both then refetch canonical state).
  Stream<NotificationIntent> get intents => _intents.stream;

  StreamSubscription<String>? _refreshSub;
  StreamSubscription<PushMessage>? _fgSub;
  StreamSubscription<PushMessage>? _openedSub;
  bool _authed = false;
  String? _lastRegisteredToken;

  bool get isAvailable => _messaging.isAvailable;

  /// Called once at startup — BEFORE authentication. Wires listeners and the
  /// cold-start message, but does not register a token yet (§17).
  Future<void> bootstrap() async {
    final ready = await _messaging.initialize();
    if (!ready) {
      dev.log(
        'NotificationCoordinator: messaging unavailable (no config).',
        name: 'sirengrid.fcm',
      );
      return;
    }
    await _syncPermission();

    _fgSub = _messaging.onForegroundMessage.listen(_onForeground);
    _openedSub = _messaging.onMessageOpenedApp.listen(
      (m) => _emit(m, tap: true),
    );
    _refreshSub = _messaging.onTokenRefresh.listen(_onTokenRefresh);

    final initial = await _messaging.getInitialMessage();
    if (initial != null) {
      // Deliver after the first frame so the app can route it.
      scheduleMicrotask(() => _emit(initial, tap: true));
    }
  }

  /// Called by [AuthCubit] once a valid session exists (§17). Safe to call
  /// repeatedly. Never throws to the caller.
  Future<void> onAuthenticated() async {
    _authed = true;
    if (!_messaging.isAvailable) {
      // Still record a pending token if one was cached earlier.
      final pending = await SecureStore.readPendingDeviceToken();
      if (pending != null) {
        /* will register when Firebase becomes available */
      }
      return;
    }
    try {
      final token =
          await _messaging.getToken() ??
          await SecureStore.readPendingDeviceToken();
      if (token == null || token.isEmpty) return;
      await SecureStore.savePendingDeviceToken(token);
      final ok = await _registrar.register(token);
      if (ok) {
        _lastRegisteredToken = token;
        await SecureStore.clearPendingDeviceToken();
      }
    } catch (e) {
      dev.log('onAuthenticated register failed: $e', name: 'sirengrid.fcm');
    }
  }

  /// Called by [AuthCubit] before the session is cleared, while the bearer is
  /// still valid — best effort so a second citizen on this device does not keep
  /// receiving the previous citizen's notifications (§10, privacy edge).
  Future<void> onLoggedOut() async {
    _authed = false;
    final token =
        _lastRegisteredToken ?? await SecureStore.readPendingDeviceToken();
    if (token != null && token.isNotEmpty) {
      await _registrar.unregister(token);
    }
    _lastRegisteredToken = null;
  }

  Future<void> requestPermission() async {
    if (!_messaging.isAvailable) return;
    final p = await _messaging.requestPermission();
    emit(_state(p));
    if (state == NotificationPermissionState.authorized && _authed) {
      await onAuthenticated();
    }
  }

  Future<void> _syncPermission() async {
    emit(_state(await _messaging.currentPermission()));
  }

  Future<void> _onTokenRefresh(String token) async {
    await SecureStore.savePendingDeviceToken(token);
    if (_authed) {
      final ok = await _registrar.register(token);
      if (ok) {
        _lastRegisteredToken = token;
        await SecureStore.clearPendingDeviceToken();
      }
    }
  }

  void _onForeground(PushMessage m) => _emit(m, tap: false);

  void _emit(PushMessage m, {required bool tap}) {
    _intents.add(
      NotificationIntent(
        type: m.type,
        requestId: m.requestId,
        alertId: m.alertId,
        title: m.title,
        body: m.body,
        fromTap: tap,
      ),
    );
  }

  NotificationPermissionState _state(PushPermission p) => switch (p) {
    PushPermission.authorized => NotificationPermissionState.authorized,
    PushPermission.provisional => NotificationPermissionState.provisional,
    PushPermission.denied => NotificationPermissionState.denied,
    PushPermission.notDetermined => NotificationPermissionState.unknown,
  };

  @override
  Future<void> close() {
    _fgSub?.cancel();
    _openedSub?.cancel();
    _refreshSub?.cancel();
    _intents.close();
    return super.close();
  }
}
