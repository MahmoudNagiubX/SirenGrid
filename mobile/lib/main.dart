import 'dart:async';
import 'dart:developer' as dev;
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'app/app.dart';
import 'core/api_client.dart';
import 'core/services.dart';

export 'app/app.dart' show SirenGridCitizenApp;

void main() {
  // Global error boundary: catches unhandled async errors and logs them calmly
  runZonedGuarded(() async {
    WidgetsFlutterBinding.ensureInitialized();

    // Initialize Firebase (fails gracefully if config is not yet supplied in dev)
    try {
      await Firebase.initializeApp();
    } catch (e) {
      dev.log('Firebase init skipped or unconfigured: $e');
    }

    final apiClient = ApiClient();
    final fcmService = FcmService(apiClient);
    fcmService.init();

    runApp(SirenGridCitizenApp(apiClient: apiClient));
  }, (error, stackTrace) {
    dev.log('Global async error caught: $error');
  });
}
