// PLACEHOLDER — replaced by `flutterfire configure` once a real SirenGrid
// Firebase project + google-services.json are available (addendum §5/§19).
//
// Until then `DefaultFirebaseOptions.currentPlatform` throws, which
// `FirebaseMessagingPort` catches so the app runs with FCM cleanly disabled
// rather than crashing on startup.
//
// ignore_for_file: type=lint
import 'package:firebase_core/firebase_core.dart' show FirebaseOptions;

class DefaultFirebaseOptions {
  const DefaultFirebaseOptions._();

  static FirebaseOptions get currentPlatform {
    throw UnsupportedError(
      'Firebase is not configured for this build. Run `flutterfire configure` '
      'with a real SirenGrid Firebase project to generate this file.',
    );
  }
}
