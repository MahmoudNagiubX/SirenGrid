import 'package:flutter/foundation.dart';

/// Runtime configuration. Everything here is compile-time (`--dart-define`) so a
/// physical device build can point at a reachable backend without editing source.
///
/// Emulator:        (default) http://10.0.2.2:8000
/// Physical device: flutter run --dart-define=API_URL=`http://<pc-lan-ip>:8000`
class AppConfig {
  const AppConfig._();

  /// Backend origin, no `/api/v1` suffix and no trailing slash.
  static final String apiBaseUrl = _stripTrailingSlash(
    const String.fromEnvironment(
      'API_URL',
      defaultValue: 'http://10.0.2.2:8000',
    ),
  );

  static const String apiPrefix = '/api/v1';

  /// Full mobile API root, e.g. `http://10.0.2.2:8000/api/v1/mobile`.
  static String get mobileApiRoot => '$apiBaseUrl$apiPrefix/mobile';

  static const String appVersion = '1.0.0';

  static const Duration httpTimeout = Duration(seconds: 12);

  /// Foreground tracking poll cadence (brief §4.5 / donor: 3–5s).
  static const Duration trackingPollInterval = Duration(seconds: 4);

  static bool get isRelease => kReleaseMode;

  static String _stripTrailingSlash(String value) =>
      value.endsWith('/') ? value.substring(0, value.length - 1) : value;
}
