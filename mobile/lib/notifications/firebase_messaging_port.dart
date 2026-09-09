import 'dart:async';
import 'dart:developer' as dev;

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';

import 'firebase_options.dart';
import 'messaging_port.dart';

/// Returns the generated FlutterFire options, or `null` when the project has
/// not been `flutterfire configure`d yet (the placeholder throws). Keeps the
/// whole app runnable without real Firebase config (addendum §15).
FirebaseOptions? _optionsOrNull() {
  try {
    return DefaultFirebaseOptions.currentPlatform;
  } on Object {
    return null;
  }
}

/// Top-level background message handler (addendum §7.H). Must be a top-level or
/// static function annotated for the AOT entry-point, and must initialise
/// Firebase itself. It does NOT touch UI or app state — the app refetches
/// canonical backend state when it next resumes.
@pragma('vm:entry-point')
Future<void> sgFirebaseBackgroundHandler(RemoteMessage message) async {
  try {
    await Firebase.initializeApp(options: _optionsOrNull());
  } catch (_) {
    /* handler still returns cleanly */
  }
  dev.log('BG push: ${message.data['type']}', name: 'sirengrid.fcm');
}

PushMessage _toPush(RemoteMessage m) => PushMessage(
  data: m.data,
  title: m.notification?.title,
  body: m.notification?.body,
);

PushPermission _map(AuthorizationStatus s) => switch (s) {
  AuthorizationStatus.authorized => PushPermission.authorized,
  AuthorizationStatus.provisional => PushPermission.provisional,
  AuthorizationStatus.denied => PushPermission.denied,
  _ => PushPermission.notDetermined,
};

/// Real implementation. Initialisation fails soft: if `firebase_options.dart`
/// has no real config yet, [initialize] returns false and the rest of the app
/// carries on (addendum §15 / §21).
class FirebaseMessagingPort implements MessagingPort {
  bool _ready = false;

  @override
  bool get isAvailable => _ready;

  @override
  Future<bool> initialize() async {
    if (_ready) return true;
    final options = _optionsOrNull();
    if (options == null) {
      dev.log(
        'Firebase client config not present — FCM disabled.',
        name: 'sirengrid.fcm',
      );
      return false;
    }
    try {
      if (Firebase.apps.isEmpty) {
        await Firebase.initializeApp(options: options);
      }
      FirebaseMessaging.onBackgroundMessage(sgFirebaseBackgroundHandler);
      await FirebaseMessaging.instance
          .setForegroundNotificationPresentationOptions(
            alert: false, // we present our own in-app SGAlertBanner (addendum §7.E)
            badge: true,
            sound: true,
          );
      _ready = true;
      return true;
    } catch (e) {
      dev.log('Firebase init failed: $e', name: 'sirengrid.fcm');
      return false;
    }
  }

  @override
  Future<PushPermission> currentPermission() async {
    if (!_ready) return PushPermission.notDetermined;
    final s = await FirebaseMessaging.instance.getNotificationSettings();
    return _map(s.authorizationStatus);
  }

  @override
  Future<PushPermission> requestPermission() async {
    if (!_ready) return PushPermission.notDetermined;
    final s = await FirebaseMessaging.instance.requestPermission(
      alert: true,
      badge: true,
      sound: true,
    );
    return _map(s.authorizationStatus);
  }

  @override
  Future<String?> getToken() async {
    if (!_ready) return null;
    try {
      return await FirebaseMessaging.instance.getToken();
    } catch (e) {
      dev.log('getToken failed: $e', name: 'sirengrid.fcm');
      return null;
    }
  }

  @override
  Stream<String> get onTokenRefresh =>
      _ready ? FirebaseMessaging.instance.onTokenRefresh : const Stream.empty();

  @override
  Stream<PushMessage> get onForegroundMessage =>
      _ready ? FirebaseMessaging.onMessage.map(_toPush) : const Stream.empty();

  @override
  Stream<PushMessage> get onMessageOpenedApp => _ready
      ? FirebaseMessaging.onMessageOpenedApp.map(_toPush)
      : const Stream.empty();

  @override
  Future<PushMessage?> getInitialMessage() async {
    if (!_ready) return null;
    final m = await FirebaseMessaging.instance.getInitialMessage();
    return m == null ? null : _toPush(m);
  }
}
