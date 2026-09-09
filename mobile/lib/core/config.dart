import 'package:flutter/foundation.dart';

/// SirenGrid Application Configuration
/// Centralizes environment settings, emergency hotline numbers,
/// and deployment information.
class AppConfig {
  static const String env = String.fromEnvironment('ENV', defaultValue: 'dev');
  static const String apiUrl = String.fromEnvironment(
    'API_URL',
    defaultValue: 'http://10.0.2.2:8000', // Default Android emulator localhost
  );

  // Application Version
  static const String appVersion = 'v1.0.4';

  // Centralized Emergency Hotline Numbers
  static const String hotlinePolice = '122';
  static const String hotlineAmbulance = '123';
  static const String hotlineFire = '180';

  // Deployment Operations Information
  // CANONICAL CONTENT CONFLICT — DEFERRED PRODUCT DECISION:
  // Arabic canonical specifies 'عمليات القاهرة' (Cairo Operations),
  // English specifies 'Nasr City Core' (Nasr City Operations Core).
  // Preserved as an unresolved product-content discrepancy per architecture instructions.
  static const String operationsAr = 'عمليات القاهرة';
  static const String operationsEn = 'Nasr City Core';

  static bool get isDev => env == 'dev';
  static bool get isProd => env == 'prod';

  // Development Preview Mode Guard
  // Strictly permitted in debug dev mode only; false in release/production.
  static bool? overridePreviewAllowed;
  static bool get isPreviewAllowed =>
      overridePreviewAllowed ?? (kDebugMode && isDev);
}

