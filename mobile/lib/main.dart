import 'dart:async';
import 'dart:developer' as dev;

import 'package:flutter/material.dart';

import 'app/app.dart';
import 'core/api_client.dart';
import 'core/location.dart';
import 'notifications/device_registrar.dart';
import 'notifications/firebase_messaging_port.dart';
import 'notifications/messaging_port.dart';
import 'notifications/notification_coordinator.dart';

void main() {
  runZonedGuarded(
    () async {
      WidgetsFlutterBinding.ensureInitialized();

      final api = ApiClient();
      final MessagingPort messaging = FirebaseMessagingPort();
      final coordinator = NotificationCoordinator(
        messaging,
        DeviceRegistrar(api),
      );

      // Firebase init + FCM listener wiring happens here; it fails soft when no
      // client config is present so the citizen flow always runs.
      unawaited(coordinator.bootstrap());

      runApp(
        SirenGridApp(
          api: api,
          coordinator: coordinator,
          location: LocationService(),
        ),
      );
    },
    (error, stack) {
      dev.log('Uncaught: $error', name: 'sirengrid', stackTrace: stack);
    },
  );
}
