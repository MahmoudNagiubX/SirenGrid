import 'dart:convert';

import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:http/http.dart' as http;
import 'package:uuid/uuid.dart';

import '../../core/api_client.dart';
import '../../core/location.dart';
import '../../core/storage.dart';
import 'emergency_service.dart';

/// Emergency submission. Repaired from the donor's `HomeCubit`:
///  * body carries NO citizen identity (`extra="forbid"` on the backend — Codex
///    P0-02); identity is derived from the bearer session,
///  * a fresh device GPS fix is acquired at submit time (never fabricated),
///  * one lifecycle-scoped `Idempotency-Key`: generated once → persisted before
///    POST → reused on retry/ambiguous failure → cleared only on authoritative
///    success,
///  * `422` (validation / current-location contract) is handled distinctly from
///    `409` (idempotency conflict).
enum SubmitFailureKind {
  location,
  auth,
  validation,
  conflict,
  server,
  network,
  contract,
}

sealed class HomeState {
  const HomeState();
}

class HomeIdle extends HomeState {
  const HomeIdle();
}

class HomeSubmitting extends HomeState {
  const HomeSubmitting(this.service, this.idempotencyKey);
  final EmergencyService service;
  final String idempotencyKey;
}

class HomeSubmitted extends HomeState {
  const HomeSubmitted({
    required this.service,
    required this.requestId,
    required this.incidentId,
  });
  final EmergencyService service;
  final String requestId;
  final String? incidentId;
}

class HomeSubmitFailure extends HomeState {
  const HomeSubmitFailure({
    required this.service,
    required this.kind,
    required this.message,
    required this.idempotencyKey,
    required this.canRetry,
  });
  final EmergencyService service;
  final SubmitFailureKind kind;
  final String message;
  final String idempotencyKey;
  final bool canRetry;
}

class HomeCubit extends Cubit<HomeState> {
  HomeCubit(this._api, this._location) : super(const HomeIdle());

  final ApiClient _api;
  final LocationService _location;
  static const _uuid = Uuid();

  EmergencyService? _lastService;
  bool _inFlight = false;

  Future<void> submit(EmergencyService service) =>
      _submit(service, forcedKey: null);

  Future<void> retry() async {
    final svc = _lastService;
    if (svc == null) return;
    final pending = await SecureStore.readPendingIdempotencyKey();
    await _submit(svc, forcedKey: pending);
  }

  void reset() {
    _lastService = null;
    emit(const HomeIdle());
  }

  Future<void> _submit(
    EmergencyService service, {
    required String? forcedKey,
  }) async {
    if (_inFlight) return; // duplicate-tap guard
    _inFlight = true;
    _lastService = service;
    try {
      final key =
          forcedKey ??
          await SecureStore.readPendingIdempotencyKey() ??
          _uuid.v4();
      await SecureStore.savePendingIdempotencyKey(key);
      emit(HomeSubmitting(service, key));

      // 1. Fresh device GPS — throws a typed LocationFailure on any problem.
      final double lat;
      final double lon;
      final double accuracy;
      try {
        final pos = await _location.freshPosition();
        lat = pos.latitude;
        lon = pos.longitude;
        accuracy = pos.accuracy;
      } on LocationFailure catch (e) {
        emit(
          HomeSubmitFailure(
            service: service,
            kind: SubmitFailureKind.location,
            message: e.message,
            idempotencyKey: key,
            canRetry: true,
          ),
        );
        return;
      }

      // 2. Exact current contract — identity is NOT sent.
      final body = <String, dynamic>{
        'service': service.apiCode,
        'location': {'lat': lat, 'lon': lon},
        'location_accuracy_m': accuracy.isFinite && accuracy >= 0
            ? accuracy
            : null,
        'client_timestamp': DateTime.now().toUtc().toIso8601String(),
        'note': null,
      };

      final http.Response res;
      try {
        res = await _api.post(
          '/emergency-requests',
          body: body,
          idempotencyKey: key,
        );
      } catch (_) {
        // Ambiguous network failure — keep the key so a retry is idempotent.
        emit(
          HomeSubmitFailure(
            service: service,
            kind: SubmitFailureKind.network,
            message: 'confirm.err_retry',
            idempotencyKey: key,
            canRetry: true,
          ),
        );
        return;
      }

      // 3. 201 first create, 200 idempotent replay.
      if (res.statusCode == 200 || res.statusCode == 201) {
        final Map<String, dynamic> data;
        try {
          data = jsonDecode(res.body) as Map<String, dynamic>;
        } catch (_) {
          emit(
            HomeSubmitFailure(
              service: service,
              kind: SubmitFailureKind.contract,
              message: 'confirm.err_validation',
              idempotencyKey: key,
              canRetry: true,
            ),
          );
          return;
        }
        final requestId = data['request_id']?.toString();
        if (requestId == null || requestId.isEmpty) {
          emit(
            HomeSubmitFailure(
              service: service,
              kind: SubmitFailureKind.contract,
              message: 'confirm.err_validation',
              idempotencyKey: key,
              canRetry: true,
            ),
          );
          return;
        }
        await SecureStore.clearPendingIdempotencyKey();
        await SecureStore.saveActiveRequestId(requestId);
        emit(
          HomeSubmitted(
            service: service,
            requestId: requestId,
            incidentId: data['incident_id']?.toString(),
          ),
        );
        return;
      }

      // 4. Error branches.
      final kind = switch (res.statusCode) {
        401 || 403 => SubmitFailureKind.auth,
        409 => SubmitFailureKind.conflict,
        422 || 400 => SubmitFailureKind.validation,
        _ => SubmitFailureKind.server,
      };
      final message = switch (kind) {
        SubmitFailureKind.auth => 'confirm.err_auth',
        SubmitFailureKind.conflict => 'confirm.err_conflict',
        SubmitFailureKind.validation => 'confirm.err_validation',
        _ => 'confirm.err_retry',
      };
      // A 409 means the key is spent against a different payload — do NOT reuse
      // it; a fresh submit should mint a new key.
      if (kind == SubmitFailureKind.conflict) {
        await SecureStore.clearPendingIdempotencyKey();
      }
      emit(
        HomeSubmitFailure(
          service: service,
          kind: kind,
          message: message,
          idempotencyKey: key,
          canRetry:
              kind == SubmitFailureKind.server ||
              kind == SubmitFailureKind.validation,
        ),
      );
    } finally {
      _inFlight = false;
    }
  }
}
