import 'dart:async';
import 'dart:convert';

import 'package:flutter_bloc/flutter_bloc.dart';

import '../../core/api_client.dart';
import '../../core/storage.dart';
import 'citizen_profile.dart';

/// Auth + session lifecycle. Repaired from the donor's `AuthCubit`:
///  * parses `access_token` (not the stale `session_token`),
///  * uses the current 6-field `/mobile/me` profile contract,
///  * a temporary network failure never fabricates an authenticated state,
///  * only an explicit 401/403 clears the stored session.
sealed class AuthState {
  const AuthState();
  CitizenProfile? get profile => null;
}

class AuthInitial extends AuthState {
  const AuthInitial();
}

class AuthRestoring extends AuthState {
  const AuthRestoring();
}

class Unauthenticated extends AuthState {
  const Unauthenticated({this.reason});
  final String? reason;
}

class AuthInProgress extends AuthState {
  const AuthInProgress();
}

class Authenticated extends AuthState {
  const Authenticated(this._profile);
  final CitizenProfile _profile;
  @override
  CitizenProfile get profile => _profile;
}

/// Distinguishes "your credentials were rejected" (loginFailure=true) from
/// "we could not reach the server to check" (sessionCheckFailure=true).
class AuthFailure extends AuthState {
  const AuthFailure(
    this.message, {
    this.sessionCheckFailure = false,
    this.loginFailure = false,
  });
  final String message;
  final bool sessionCheckFailure;
  final bool loginFailure;
}

typedef AfterAuthHook = Future<void> Function(CitizenProfile profile);
typedef BeforeLogoutHook = Future<void> Function();

class AuthCubit extends Cubit<AuthState> {
  AuthCubit(this._api, {this.onAuthenticated, this.onBeforeLogout})
    : super(const AuthInitial());

  final ApiClient _api;

  /// Called once a valid session is established (login or restore). Used to
  /// bind the FCM device registration to the authenticated citizen (§17).
  final AfterAuthHook? onAuthenticated;

  /// Called before the local session is cleared, so a best-effort device-token
  /// deactivation can run while the bearer is still valid (§10, privacy edge).
  final BeforeLogoutHook? onBeforeLogout;

  Future<void> restoreSession() async {
    emit(const AuthRestoring());
    final token = await SecureStore.readAccessToken();
    if (token == null || token.trim().isEmpty) {
      _api.clearAccessToken();
      emit(const Unauthenticated());
      return;
    }
    _api.setAccessToken(token);
    await _loadProfile(isRestore: true);
  }

  Future<void> login(String phone, String pin) async {
    final cleanPhone = phone.trim();
    final cleanPin = pin.trim();
    if (cleanPhone.isEmpty || cleanPin.isEmpty) {
      emit(const AuthFailure('login.err_required', loginFailure: true));
      return;
    }
    if (!RegExp(r'^\d{4}$').hasMatch(cleanPin)) {
      emit(const AuthFailure('login.err_pin', loginFailure: true));
      return;
    }

    emit(const AuthInProgress());
    try {
      final res = await _api.post(
        '/auth/login',
        body: {'phone': cleanPhone, 'pin': cleanPin},
      );
      if (res.statusCode == 200) {
        final data = jsonDecode(res.body) as Map<String, dynamic>;
        final token = data['access_token'];
        if (token is! String || token.isEmpty) {
          emit(
            const AuthFailure(
              'Contract mismatch: login response has no access_token.',
              loginFailure: true,
            ),
          );
          return;
        }
        await SecureStore.saveAccessToken(token);
        _api.setAccessToken(token);
        await _loadProfile(isRestore: false);
      } else if (res.statusCode == 401 || res.statusCode == 403) {
        emit(const AuthFailure('login.err_invalid', loginFailure: true));
      } else {
        emit(const AuthFailure('login.err_server', loginFailure: true));
      }
    } catch (_) {
      emit(const AuthFailure('login.err_network', loginFailure: true));
    }
  }

  Future<void> _loadProfile({required bool isRestore}) async {
    try {
      final res = await _api.get('/me');
      if (res.statusCode == 200) {
        final profile = CitizenProfile.fromJson(
          jsonDecode(res.body) as Map<String, dynamic>,
        );
        emit(Authenticated(profile));
        // Fire-and-forget: FCM registration must not block auth (§17).
        final hook = onAuthenticated;
        if (hook != null) {
          unawaited(hook(profile));
        }
      } else if (res.statusCode == 401 || res.statusCode == 403) {
        await SecureStore.clearAccessToken();
        _api.clearAccessToken();
        emit(Unauthenticated(reason: isRestore ? 'session_expired' : null));
      } else {
        emit(
          AuthFailure(
            'Server returned ${res.statusCode} while loading your profile.',
            sessionCheckFailure: isRestore,
            loginFailure: !isRestore,
          ),
        );
      }
    } on FormatException catch (e) {
      emit(
        AuthFailure(
          e.message,
          sessionCheckFailure: isRestore,
          loginFailure: !isRestore,
        ),
      );
    } catch (_) {
      // Network problem: keep the stored token, surface the failure honestly.
      emit(
        AuthFailure(
          isRestore
              ? 'Unable to reach SirenGrid to verify your session.'
              : 'login.err_network',
          sessionCheckFailure: isRestore,
          loginFailure: !isRestore,
        ),
      );
    }
  }

  Future<void> logout() async {
    try {
      await onBeforeLogout?.call();
    } catch (_) {
      /* best effort */
    }
    try {
      if (_api.hasSession) {
        await _api.post('/auth/logout');
      }
    } catch (_) {
      /* local clearance still proceeds */
    }
    await SecureStore.clearCitizenSession();
    _api.clearAccessToken();
    emit(const Unauthenticated());
  }
}
