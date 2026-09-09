import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Secure, persistent citizen state. Ported from the donor branch (its keys and
/// in-memory test double are sound) — session credential, active emergency
/// request id, the in-flight idempotency key, and UI preferences.
///
/// Nothing operational is cached here: the backend is always re-queried for
/// request/incident state.
class SecureStore {
  SecureStore._();

  static const _storage = FlutterSecureStorage();

  // Keys
  static const _kAccessToken = 'sg_access_token';
  static const _kActiveRequestId = 'sg_active_request_id';
  static const _kPendingIdempotencyKey = 'sg_pending_idempotency_key';
  static const _kPendingDeviceToken = 'sg_pending_device_token';
  static const _kLanguage = 'sg_language';

  /// In-memory replacement used by tests (no platform channel).
  static Map<String, String>? _mock;

  static void useInMemory([Map<String, String>? seed]) => _mock = {...?seed};

  static void reset() => _mock = null;

  static Future<void> _write(String key, String value) async {
    if (_mock != null) {
      _mock![key] = value;
      return;
    }
    await _storage.write(key: key, value: value);
  }

  static Future<String?> _read(String key) async {
    if (_mock != null) return _mock![key];
    return _storage.read(key: key);
  }

  static Future<void> _delete(String key) async {
    if (_mock != null) {
      _mock!.remove(key);
      return;
    }
    await _storage.delete(key: key);
  }

  // Session --------------------------------------------------------------------
  static Future<void> saveAccessToken(String token) =>
      _write(_kAccessToken, token);
  static Future<String?> readAccessToken() => _read(_kAccessToken);
  static Future<void> clearAccessToken() => _delete(_kAccessToken);

  // Active emergency request -------------------------------------------------
  static Future<void> saveActiveRequestId(String id) =>
      _write(_kActiveRequestId, id);
  static Future<String?> readActiveRequestId() => _read(_kActiveRequestId);
  static Future<void> clearActiveRequestId() => _delete(_kActiveRequestId);

  // Idempotency key (survives a network-ambiguous retry) --------------------
  static Future<void> savePendingIdempotencyKey(String key) =>
      _write(_kPendingIdempotencyKey, key);
  static Future<String?> readPendingIdempotencyKey() =>
      _read(_kPendingIdempotencyKey);
  static Future<void> clearPendingIdempotencyKey() =>
      _delete(_kPendingIdempotencyKey);

  // FCM token cached while unauthenticated, registered after login ----------
  static Future<void> savePendingDeviceToken(String token) =>
      _write(_kPendingDeviceToken, token);
  static Future<String?> readPendingDeviceToken() =>
      _read(_kPendingDeviceToken);
  static Future<void> clearPendingDeviceToken() =>
      _delete(_kPendingDeviceToken);

  // Preferences ------------------------------------------------------------
  static Future<void> saveLanguage(String code) => _write(_kLanguage, code);
  static Future<String?> readLanguage() => _read(_kLanguage);

  /// Wipe everything private to the previous citizen. Called on logout so a
  /// second citizen signing in on the same device inherits nothing.
  static Future<void> clearCitizenSession() async {
    await clearAccessToken();
    await clearActiveRequestId();
    await clearPendingIdempotencyKey();
    // The device push token is intentionally kept (device-scoped, re-associated
    // on next authenticated registration).
  }
}
