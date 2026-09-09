import 'dart:async';
import 'dart:developer' as dev;
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:geolocator/geolocator.dart';
import 'api_client.dart';

// ponytail: single consolidated services file replaces multiple separate files
class StorageService {
  static const _storage = FlutterSecureStorage();
  // ponytail: in-memory mock support for unit tests without external mocking framework
  static Map<String, String>? _mockStore;

  static const _activeRequestKey = 'active_emergency_request_id';
  static const _idempotencyKey = 'pending_idempotency_uuid';
  static const _sessionCredentialKey = 'sirengrid_session_credential';

  static void enableMockStorage([Map<String, String>? initialData]) {
    _mockStore = initialData != null ? Map<String, String>.from(initialData) : <String, String>{};
  }

  static void resetStorage() {
    _mockStore = null;
  }

  static Future<void> saveSessionCredential(String credential) async {
    if (_mockStore != null) {
      _mockStore![_sessionCredentialKey] = credential;
      return;
    }
    await _storage.write(key: _sessionCredentialKey, value: credential);
  }

  static Future<String?> getSessionCredential() async {
    if (_mockStore != null) {
      return _mockStore![_sessionCredentialKey];
    }
    return await _storage.read(key: _sessionCredentialKey);
  }

  static Future<bool> hasSessionCredential() async {
    final cred = await getSessionCredential();
    return cred != null && cred.isNotEmpty;
  }

  static Future<void> clearSessionCredential() async {
    if (_mockStore != null) {
      _mockStore!.remove(_sessionCredentialKey);
      return;
    }
    await _storage.delete(key: _sessionCredentialKey);
  }

  static Future<void> saveActiveRequestId(String id) async {
    if (_mockStore != null) {
      _mockStore![_activeRequestKey] = id;
      return;
    }
    await _storage.write(key: _activeRequestKey, value: id);
  }

  static Future<String?> getActiveRequestId() async {
    if (_mockStore != null) {
      return _mockStore![_activeRequestKey];
    }
    return await _storage.read(key: _activeRequestKey);
  }

  static Future<void> clearActiveRequestId() async {
    if (_mockStore != null) {
      _mockStore!.remove(_activeRequestKey);
      return;
    }
    await _storage.delete(key: _activeRequestKey);
  }

  static Future<void> savePendingIdempotencyKey(String key) async {
    if (_mockStore != null) {
      _mockStore![_idempotencyKey] = key;
      return;
    }
    await _storage.write(key: _idempotencyKey, value: key);
  }

  static Future<String?> getPendingIdempotencyKey() async {
    if (_mockStore != null) {
      return _mockStore![_idempotencyKey];
    }
    return await _storage.read(key: _idempotencyKey);
  }

  static Future<void> clearPendingIdempotencyKey() async {
    if (_mockStore != null) {
      _mockStore!.remove(_idempotencyKey);
      return;
    }
    await _storage.delete(key: _idempotencyKey);
  }

  static const _languageKey = 'sirengrid_user_language';
  static const _themeKey = 'sirengrid_user_theme';

  static Future<void> saveLanguagePreference(String pref) async {
    if (_mockStore != null) {
      _mockStore![_languageKey] = pref;
      return;
    }
    await _storage.write(key: _languageKey, value: pref);
  }

  static Future<String?> getLanguagePreference() async {
    if (_mockStore != null) {
      return _mockStore![_languageKey];
    }
    return await _storage.read(key: _languageKey);
  }

  static Future<void> saveThemePreference(String pref) async {
    if (_mockStore != null) {
      _mockStore![_themeKey] = pref;
      return;
    }
    await _storage.write(key: _themeKey, value: pref);
  }

  static Future<String?> getThemePreference() async {
    if (_mockStore != null) {
      return _mockStore![_themeKey];
    }
    return await _storage.read(key: _themeKey);
  }
}

// ponytail: typed location exceptions for truthful error handling
abstract class LocationException implements Exception {
  final String message;
  const LocationException(this.message);
  @override
  String toString() => message;
}

class LocationServicesDisabledException extends LocationException {
  const LocationServicesDisabledException([super.message = 'Location services are disabled. Please enable GPS in device settings.']);
}

class LocationPermissionDeniedException extends LocationException {
  const LocationPermissionDeniedException([super.message = 'Location permission is required to send emergency services.']);
}

class LocationPermissionPermanentlyDeniedException extends LocationException {
  const LocationPermissionPermanentlyDeniedException([super.message = 'Location permissions are permanently denied. Please enable them in device settings.']);
}

class LocationAcquisitionException extends LocationException {
  const LocationAcquisitionException([super.message = 'Failed to acquire GPS location.']);
}

enum LocationReadinessResult {
  ready,
  disabled,
  permissionRequired,
  permissionDeniedForever,
  unavailable,
}

class LocationService {
  // ponytail: in-memory mock support for unit tests without external mocking framework
  static Position? _mockPosition;
  static LocationPermission? _mockPermission;
  static bool? _mockServiceEnabled;
  static Object? _mockError;

  static void enableMockLocation({
    Position? position,
    LocationPermission? permission,
    bool? serviceEnabled,
    Object? error,
  }) {
    _mockPosition = position;
    _mockPermission = permission;
    _mockServiceEnabled = serviceEnabled;
    _mockError = error;
  }

  static void resetMockLocation() {
    _mockPosition = null;
    _mockPermission = null;
    _mockServiceEnabled = null;
    _mockError = null;
  }

  static Future<bool> isLocationServiceEnabled() async {
    if (_mockServiceEnabled != null) return _mockServiceEnabled!;
    return await Geolocator.isLocationServiceEnabled();
  }

  static Future<LocationPermission> checkPermission() async {
    if (_mockPermission != null) return _mockPermission!;
    return await Geolocator.checkPermission();
  }

  static Future<LocationPermission> requestPermission() async {
    if (_mockPermission != null) return _mockPermission!;
    return await Geolocator.requestPermission();
  }

  static Future<LocationReadinessResult> checkReadiness() async {
    if (_mockError != null) return LocationReadinessResult.unavailable;
    final enabled = await isLocationServiceEnabled();
    if (!enabled) return LocationReadinessResult.disabled;
    final permission = await checkPermission();
    if (permission == LocationPermission.deniedForever) {
      return LocationReadinessResult.permissionDeniedForever;
    }
    if (permission == LocationPermission.denied) {
      return LocationReadinessResult.permissionRequired;
    }
    return LocationReadinessResult.ready;
  }

  static Future<Position> getCurrentLocation({Duration timeout = const Duration(seconds: 10)}) async {
    if (_mockError != null) {
      throw _mockError!;
    }
    if (_mockPosition != null) {
      return _mockPosition!;
    }

    final enabled = await isLocationServiceEnabled();
    if (!enabled) {
      throw const LocationServicesDisabledException();
    }

    var permission = await checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await requestPermission();
      if (permission == LocationPermission.denied) {
        throw const LocationPermissionDeniedException();
      }
    }

    if (permission == LocationPermission.deniedForever) {
      throw const LocationPermissionPermanentlyDeniedException();
    }

    try {
      return await Geolocator.getCurrentPosition(
        locationSettings: LocationSettings(
          accuracy: LocationAccuracy.high,
          timeLimit: timeout,
        ),
      );
    } on TimeoutException {
      throw const LocationAcquisitionException('GPS acquisition timed out. Please retry.');
    } catch (e) {
      throw LocationAcquisitionException('Failed to acquire GPS location: $e');
    }
  }
}

class FcmService {
  final ApiClient _apiClient;
  FcmService(this._apiClient);

  Future<void> init() async {
    try {
      final messaging = FirebaseMessaging.instance;
      final settings = await messaging.requestPermission(alert: true, badge: true, sound: true);

      if (settings.authorizationStatus == AuthorizationStatus.authorized) {
        final token = await messaging.getToken();
        if (token != null) {
          await _registerTokenWithBackend(token);
        }

        // Listen for token refresh
        messaging.onTokenRefresh.listen((newToken) {
          _registerTokenWithBackend(newToken);
        });
      }
    } catch (e) {
      dev.log('FCM setup error: $e');
    }
  }

  Future<void> _registerTokenWithBackend(String token) async {
    try {
      await _apiClient.post('/api/v1/mobile/me/fcm-token', body: {'fcm_token': token});
    } catch (e) {
      dev.log('Failed to register FCM token with FastAPI: $e');
    }
  }
}
