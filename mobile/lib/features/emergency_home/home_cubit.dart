import 'dart:convert';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:geolocator/geolocator.dart';
import 'package:uuid/uuid.dart';
import '../../core/api_client.dart';
import '../../core/services.dart';
import 'emergency_service.dart';

enum HomeErrorType {
  location,
  auth,
  invalidRequest,
  conflict,
  server,
  network,
  contractMismatch,
}

abstract class HomeState {
  const HomeState();
}

class HomeInitial extends HomeState {
  const HomeInitial();
}

class HomeSubmitting extends HomeState {
  final String idempotencyKey;
  final EmergencyService? service;

  const HomeSubmitting(this.idempotencyKey, {this.service});
}

class HomeSubmitted extends HomeState {
  final String requestId;
  final EmergencyService? service;
  final Map<String, dynamic> data;

  const HomeSubmitted(this.requestId, {this.service, this.data = const {}});
}

class HomeError extends HomeState {
  final String message;
  final String idempotencyKey;
  final EmergencyService? service;
  final HomeErrorType errorType;

  const HomeError(
    this.message,
    this.idempotencyKey, {
    this.service,
    this.errorType = HomeErrorType.network,
  });
}

class HomeCubit extends Cubit<HomeState> {
  final ApiClient _apiClient;
  EmergencyService? _lastService;
  String? _lastCitizenReference;

  HomeCubit(this._apiClient) : super(const HomeInitial());

  EmergencyService? get lastService => _lastService;

  // ponytail: lifecycle-tied UUID: generate once -> persist before POST -> reuse on retry/timeout -> discard on authoritative success
  Future<void> submitEmergency({
    required EmergencyService service,
    String? citizenReference,
    String? forcedKey,
  }) async {
    // Keep selected emergency stable
    _lastService = service;
    _lastCitizenReference = citizenReference;

    // 1. Get or generate Idempotency UUID
    final String key = forcedKey ?? await StorageService.getPendingIdempotencyKey() ?? const Uuid().v4();
    await StorageService.savePendingIdempotencyKey(key);

    emit(HomeSubmitting(key, service: service));

    // 2. Fetch fresh device GPS location (Truthful: never fake coordinates)
    final Position position;
    try {
      position = await LocationService.getCurrentLocation();
    } on LocationException catch (e) {
      emit(HomeError(e.message, key, service: service, errorType: HomeErrorType.location));
      return;
    } catch (e) {
      emit(HomeError('Location acquisition error: $e', key, service: service, errorType: HomeErrorType.location));
      return;
    }

    // 3. Exact frozen request contract (Master Plan v2.1 §14.1)
    final payload = {
      'citizen_reference': citizenReference ?? 'demo-citizen-001',
      'service': service.backendServiceCode,
      'location': {
        'lat': position.latitude,
        'lon': position.longitude,
      },
      'location_accuracy_m': position.accuracy,
      'client_timestamp': DateTime.now().toUtc().toIso8601String(),
      'note': null,
    };

    // 4. Dispatch to backend with Authorization header and Idempotency-Key
    final dynamic httpResponse;
    try {
      httpResponse = await _apiClient.post(
        '/api/v1/mobile/emergency-requests',
        body: payload,
        idempotencyKey: key,
      );
    } catch (e) {
      // Network/timeout error: preserve the same idempotency key for safe retry!
      emit(HomeError(
        'Network error or timeout. Your emergency request key is preserved. Please retry.',
        key,
        service: service,
        errorType: HomeErrorType.network,
      ));
      return;
    }

    // 5. Authoritative response handling (Zero synthetic fallback)
    if (httpResponse.statusCode == 200 || httpResponse.statusCode == 201) {
      final Map<String, dynamic> data;
      try {
        data = jsonDecode(httpResponse.body) as Map<String, dynamic>;
      } catch (e) {
        emit(HomeError(
          'Contract mismatch: Non-JSON response from emergency server.',
          key,
          service: service,
          errorType: HomeErrorType.contractMismatch,
        ));
        return;
      }

      final rawRequestId = data['request_id'];
      if (rawRequestId == null || rawRequestId.toString().trim().isEmpty) {
        emit(HomeError(
          'Contract mismatch: Missing authoritative request_id in backend response.',
          key,
          service: service,
          errorType: HomeErrorType.contractMismatch,
        ));
        return;
      }

      final requestId = rawRequestId.toString();

      // 6. Success -> discard UUID and save authoritative active request ID
      await StorageService.clearPendingIdempotencyKey();
      await StorageService.saveActiveRequestId(requestId);

      emit(HomeSubmitted(requestId, service: service, data: data));
    } else if (httpResponse.statusCode == 401) {
      emit(HomeError(
        'Authentication session expired or invalid. Please log in again.',
        key,
        service: service,
        errorType: HomeErrorType.auth,
      ));
    } else if (httpResponse.statusCode == 400) {
      emit(HomeError(
        'Invalid emergency request (${httpResponse.statusCode}).',
        key,
        service: service,
        errorType: HomeErrorType.invalidRequest,
      ));
    } else if (httpResponse.statusCode == 409) {
      emit(HomeError(
        'Conflict: Submission key already used with conflicting payload.',
        key,
        service: service,
        errorType: HomeErrorType.conflict,
      ));
    } else {
      emit(HomeError(
        'Emergency server error (${httpResponse.statusCode}). You can retry safely.',
        key,
        service: service,
        errorType: HomeErrorType.server,
      ));
    }
  }

  // Convenience method for string-based calls or retries
  Future<void> submitEmergencyRequest(String serviceCode, {String? retryKey, String? citizenReference}) async {
    final service = EmergencyService.fromBackendCode(serviceCode);
    await submitEmergency(service: service, citizenReference: citizenReference, forcedKey: retryKey);
  }

  Future<void> retryLastSubmission() async {
    if (_lastService != null) {
      final pendingKey = await StorageService.getPendingIdempotencyKey();
      await submitEmergency(
        service: _lastService!,
        citizenReference: _lastCitizenReference,
        forcedKey: pendingKey,
      );
    }
  }

  Future<void> reset() async {
    _lastService = null;
    _lastCitizenReference = null;
    await StorageService.clearPendingIdempotencyKey();
    emit(const HomeInitial());
  }
}
