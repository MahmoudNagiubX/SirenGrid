import 'dart:convert';
import 'package:flutter_bloc/flutter_bloc.dart';
import '../../core/api_client.dart';
import '../../core/config.dart';
import '../../core/dev_preview.dart';
import '../../core/services.dart';

// BACKEND CONTRACT GAP — REGISTERED ADDRESS
// The mobile Account specification requires a registered address field, but the
// /api/v1/mobile/me backend contract does not contain it. The field is deferred and
// remains unavailable rather than fabricating synthetic or GPS-derived address data.

// ponytail: minimal profile model based strictly on /api/v1/mobile/me contract
class CitizenProfile {
  final String citizenReference;
  final String displayName;
  final String phone;
  final String maskedNationalId;
  final String status;
  final String dataReality;

  const CitizenProfile({
    required this.citizenReference,
    required this.displayName,
    required this.phone,
    required this.maskedNationalId,
    required this.status,
    this.dataReality = 'DEMO',
  });

  factory CitizenProfile.fromJson(Map<String, dynamic> json) {
    // ponytail: strict contract parsing — fail explicitly on missing required fields.
    // Reject speculative aliases (e.g. id, full_name, masked_national_id).
    final citizenRef = json['citizen_reference'] as String?;
    final displayName = json['display_name'] as String?;
    final phone = json['phone'] as String?;
    final nationalIdLast4 = json['national_id_last4'] as String?;
    final identityStatus = json['identity_status'] as String?;
    final dataReality = json['data_reality'] as String?;

    if (citizenRef == null ||
        displayName == null ||
        phone == null ||
        nationalIdLast4 == null ||
        identityStatus == null ||
        dataReality == null) {
      throw const FormatException(
        'Contract mismatch: /api/v1/mobile/me response missing required fields. Expected: '
        'citizen_reference, display_name, phone, national_id_last4, identity_status, data_reality',
      );
    }

    return CitizenProfile(
      citizenReference: citizenRef,
      displayName: displayName,
      phone: phone,
      maskedNationalId: '•••• •••• •••• $nationalIdLast4',
      status: identityStatus,
      dataReality: dataReality,
    );
  }

  Map<String, dynamic> toJson() => {
    'citizen_reference': citizenReference,
    'display_name': displayName,
    'phone': phone,
    'national_id_last4': maskedNationalId.replaceAll('•••• •••• •••• ', ''),
    'identity_status': status,
    'data_reality': dataReality,
  };
}

abstract class AuthState {
  const AuthState();
  CitizenProfile? get profile => null;
}

class AuthInitial extends AuthState {
  const AuthInitial();
}

class AuthCheckingSession extends AuthState {
  const AuthCheckingSession();
}

class Unauthenticated extends AuthState {
  const Unauthenticated();
}

class Authenticating extends AuthState {
  const Authenticating();
}

// ponytail: alias AuthLoading to Authenticating for UI compatibility
typedef AuthLoading = Authenticating;

class Authenticated extends AuthState {
  @override
  final CitizenProfile profile;
  const Authenticated(this.profile);
}

/// Development-Only UI Preview State
/// Strictly isolated from Authenticated state.
/// Holds static mock citizen profile for offline UI inspection.
class AuthPreview extends AuthState {
  @override
  final CitizenProfile profile;
  const AuthPreview(this.profile);
}

class AuthFailure extends AuthState {
  final String message;
  final bool isSessionCheckFailure;
  const AuthFailure(this.message, {this.isSessionCheckFailure = false});
}

// ponytail: subclass AuthError from AuthFailure for UI compatibility
class AuthError extends AuthFailure {
  const AuthError(super.message, {super.isSessionCheckFailure});
}

class AuthCubit extends Cubit<AuthState> {
  final ApiClient _apiClient;

  AuthCubit(this._apiClient) : super(const AuthInitial());

  /// Checks whether an existing session credential is saved in secure storage,
  /// validates it against GET /api/v1/mobile/me, and restores authenticated state.
  Future<void> checkSession() async {
    emit(const AuthCheckingSession());
    try {
      final credential = await StorageService.getSessionCredential();
      if (credential == null || credential.trim().isEmpty) {
        _apiClient.clearSessionCredential();
        emit(const Unauthenticated());
        return;
      }

      _apiClient.setSessionCredential(credential);
      final res = await _apiClient.get('/api/v1/mobile/me');

      if (res.statusCode == 200) {
        final data = jsonDecode(res.body) as Map<String, dynamic>;
        emit(Authenticated(CitizenProfile.fromJson(data)));
      } else if (res.statusCode == 401 || res.statusCode == 403) {
        // Expired or invalid credential -> clear session
        await StorageService.clearSessionCredential();
        _apiClient.clearSessionCredential();
        emit(const Unauthenticated());
      } else {
        // Non-auth server error: do NOT destroy local session, represent failure truthfully
        emit(AuthFailure(
          'Server returned status ${res.statusCode} during session check.',
          isSessionCheckFailure: true,
        ));
      }
    } on FormatException catch (e) {
      emit(AuthFailure(e.message, isSessionCheckFailure: true));
    } catch (e) {
      // Network or connection error: do NOT silently fallback to synthetic profile!
      // Do NOT destroy stored session unless backend explicitly rejects credential with 401/403.
      emit(const AuthFailure(
        'Unable to connect to SirenGrid server to verify session.',
        isSessionCheckFailure: true,
      ));
    }
  }

  Future<void> fetchProfile() async {
    try {
      final res = await _apiClient.get('/api/v1/mobile/me');
      if (res.statusCode == 200) {
        final data = jsonDecode(res.body) as Map<String, dynamic>;
        emit(Authenticated(CitizenProfile.fromJson(data)));
      } else if (res.statusCode == 401 || res.statusCode == 403) {
        await StorageService.clearSessionCredential();
        _apiClient.clearSessionCredential();
        emit(const Unauthenticated());
      } else {
        emit(AuthFailure('Failed to retrieve profile (${res.statusCode}).'));
      }
    } on FormatException catch (e) {
      emit(AuthFailure(e.message));
    } catch (e) {
      emit(AuthFailure('Failed to retrieve profile: $e'));
    }
  }

  Future<void> loginWithPhoneAndPin(String phone, String pin) async {
    final cleanPhone = phone.trim();
    final cleanPin = pin.trim();

    if (cleanPhone.isEmpty || cleanPin.isEmpty) {
      emit(const AuthFailure('Phone number and PIN are required.'));
      return;
    }

    // ponytail: confirmed contract constraint — PIN is exactly 4 numeric digits
    if (cleanPin.length != 4 || !RegExp(r'^\d{4}$').hasMatch(cleanPin)) {
      emit(const AuthFailure('PIN must be exactly 4 digits.'));
      return;
    }

    emit(const Authenticating());
    try {
      final res = await _apiClient.post(
        '/api/v1/mobile/auth/login',
        body: {'phone': cleanPhone, 'pin': cleanPin},
      );

      if (res.statusCode == 200) {
        final data = jsonDecode(res.body) as Map<String, dynamic>;
        // ponytail: strict contract parsing — parse confirmed session_token field only.
        // Do not accept speculative aliases (token, access_token, session_credential).
        final token = data['session_token'] as String?;

        if (token == null || token.trim().isEmpty) {
          emit(const AuthFailure('Contract mismatch: Missing session_token in /api/v1/mobile/auth/login response.'));
          return;
        }

        await StorageService.saveSessionCredential(token);
        _apiClient.setSessionCredential(token);

        await fetchProfile();
      } else if (res.statusCode == 401 || res.statusCode == 403) {
        emit(const AuthFailure('Invalid credentials. Please check your phone and PIN.'));
      } else {
        emit(AuthFailure('Login failed (Server error ${res.statusCode}).'));
      }
    } catch (e) {
      emit(AuthFailure('Connection error: Unable to reach SirenGrid server ($e).'));
    }
  }

  /// Enters development-only UI preview mode.
  /// Strictly guarded: no-op if AppConfig.isPreviewAllowed is false.
  /// Does NOT call login API, does NOT save credentials in storage,
  /// does NOT set Authorization headers.
  void enterPreviewMode() {
    if (!AppConfig.isPreviewAllowed) return;
    emit(const AuthPreview(DevPreviewConfig.previewCitizenProfile));
  }

  /// Exits development-only UI preview mode cleanly back to unauthenticated.
  void exitPreviewMode() {
    emit(const Unauthenticated());
  }

  /// Logs out the user.
  /// Confirmed local session clearance; best-effort remote server-session revocation when offline.
  Future<bool> logout() async {
    if (state is AuthPreview) {
      exitPreviewMode();
      return true;
    }

    bool remoteRevocationSucceeded = false;
    try {
      if (_apiClient.hasSessionCredential) {
        final res = await _apiClient.post('/api/v1/mobile/auth/logout');
        remoteRevocationSucceeded = (res.statusCode == 200 || res.statusCode == 204);
      }
    } catch (_) {
      // Remote logout failed (network offline / server down). Local session is still cleared.
      remoteRevocationSucceeded = false;
    } finally {
      await StorageService.clearSessionCredential();
      _apiClient.clearSessionCredential();
      emit(const Unauthenticated());
    }
    return remoteRevocationSucceeded;
  }
}
