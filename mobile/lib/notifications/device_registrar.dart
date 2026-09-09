import 'dart:developer' as dev;
import 'dart:io' show Platform;

import '../core/api_client.dart';
import '../core/config.dart';

/// Talks to the single canonical authenticated device-token contract on the
/// backend (added by this mission — no equivalent existed on `origin/main`):
///
///   POST   /api/v1/mobile/devices/register    {token, platform, app_version}
///   POST   /api/v1/mobile/devices/unregister  {token}
///
/// Identity is derived from the bearer session — the body never carries citizen
/// identity (addendum §9). All calls are best-effort: a failure here must never
/// block login, emergency submission or tracking (addendum §17).
class DeviceRegistrar {
  DeviceRegistrar(this._api);

  final ApiClient _api;

  String get _platform => Platform.isIOS ? 'IOS' : 'ANDROID';

  Future<bool> register(String token) async {
    if (token.isEmpty || !_api.hasSession) return false;
    try {
      final res = await _api.post(
        '/devices/register',
        body: {
          'token': token,
          'platform': _platform,
          'app_version': AppConfig.appVersion,
        },
      );
      final ok = res.statusCode == 200 || res.statusCode == 201;
      if (!ok) {
        dev.log('device register -> ${res.statusCode}', name: 'sirengrid.fcm');
      }
      return ok;
    } catch (e) {
      dev.log('device register failed: $e', name: 'sirengrid.fcm');
      return false;
    }
  }

  Future<bool> unregister(String token) async {
    if (token.isEmpty || !_api.hasSession) return false;
    try {
      final res = await _api.post(
        '/devices/unregister',
        body: {'token': token},
      );
      return res.statusCode == 200 || res.statusCode == 204;
    } catch (e) {
      dev.log('device unregister failed: $e', name: 'sirengrid.fcm');
      return false;
    }
  }
}
