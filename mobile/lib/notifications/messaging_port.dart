import 'dart:async';

/// Provider-agnostic view of an inbound push message. The app never treats push
/// content as operational truth — it carries a `type` and identifiers, and the
/// app refetches the backend (addendum §14/§19).
class PushMessage {
  const PushMessage({this.data = const {}, this.title, this.body});
  final Map<String, dynamic> data;
  final String? title;
  final String? body;

  String get type => (data['type'] ?? '').toString().toUpperCase();
  String? get requestId => data['request_id']?.toString();
  String? get incidentId => data['incident_id']?.toString();
  String? get alertId => data['alert_id']?.toString();
}

enum PushPermission { authorized, provisional, denied, notDetermined }

/// Injectable seam over `firebase_messaging`. Tests provide a fake; production
/// uses [FirebaseMessagingPort]. Keeping this abstract means the whole app
/// compiles and runs even when Firebase client config is absent.
abstract class MessagingPort {
  /// Initialise the underlying SDK (Firebase.initializeApp + messaging setup).
  /// Returns false if configuration is missing / init failed — the app must
  /// continue regardless.
  Future<bool> initialize();

  bool get isAvailable;

  Future<PushPermission> currentPermission();
  Future<PushPermission> requestPermission();

  Future<String?> getToken();
  Stream<String> get onTokenRefresh;

  Stream<PushMessage> get onForegroundMessage;
  Stream<PushMessage> get onMessageOpenedApp;
  Future<PushMessage?> getInitialMessage();
}
