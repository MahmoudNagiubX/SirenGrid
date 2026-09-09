import 'dart:async';
import 'dart:convert';

import 'package:flutter_bloc/flutter_bloc.dart';

import '../../core/api_client.dart';
import '../../core/config.dart';
import '../../core/storage.dart';
import 'tracking_models.dart';

/// Polls `GET /mobile/emergency-requests/{id}` while the Track tab is visible.
/// Ported from the donor's `TrackingCubit` (its 4s cadence, overlap guard and
/// terminal cleanup are sound), upgraded to the current tracking contract and
/// made resilient to repeated errors.
///
/// It never computes route/ETA/assignment — the backend is the only truth. The
/// UI may interpolate the *displayed* responder marker between two backend
/// snapshots for smoothness; the next snapshot always reconciles it.
sealed class TrackingState {
  const TrackingState();
}

class TrackingIdle extends TrackingState {
  const TrackingIdle();
}

class TrackingLoading extends TrackingState {
  const TrackingLoading();
}

class TrackingReady extends TrackingState {
  const TrackingReady(this.snapshot, {this.stalePolls = 0});
  final TrackingSnapshot snapshot;

  /// Consecutive failed refreshes since the last good snapshot (drives a
  /// "may be out of date" hint without dropping the last known state).
  final int stalePolls;
}

class TrackingUnavailable extends TrackingState {
  const TrackingUnavailable(this.message, {this.recoverable = true});
  final String message;
  final bool recoverable;
}

class TrackingCubit extends Cubit<TrackingState> {
  TrackingCubit(this._api, {Duration? pollInterval})
    : _interval = pollInterval ?? AppConfig.trackingPollInterval,
      super(const TrackingIdle());

  final ApiClient _api;
  final Duration _interval;

  Timer? _timer;
  bool _fetching = false;
  String? _requestId;
  int _errorStreak = 0;

  String? get requestId => _requestId;

  Future<void> start({String? requestId}) async {
    final id = requestId ?? await SecureStore.readActiveRequestId();
    if (id == null || id.isEmpty) {
      _stop();
      _requestId = null;
      emit(const TrackingIdle());
      return;
    }
    if (id == _requestId && _timer != null) {
      // Already tracking this request; just refresh immediately.
      await _fetch();
      return;
    }
    _requestId = id;
    _errorStreak = 0;
    if (state is! TrackingReady) emit(const TrackingLoading());
    _stop();
    await _fetch();
    if (_isTerminal) return;
    _timer = Timer.periodic(_interval, (_) => _fetch());
  }

  /// Immediate out-of-band refresh (lifecycle resume, push received).
  Future<void> refreshNow() async {
    if (_requestId == null) {
      await start();
      return;
    }
    await _fetch();
  }

  Future<void> stopAndClear() async {
    _stop();
    _requestId = null;
    await SecureStore.clearActiveRequestId();
    emit(const TrackingIdle());
  }

  void pause() => _stop();

  bool get _isTerminal =>
      state is TrackingReady &&
      (state as TrackingReady).snapshot.status.isTerminal;

  Future<void> _fetch() async {
    final id = _requestId;
    if (id == null || _fetching) return;
    _fetching = true;
    try {
      final res = await _api.get('/emergency-requests/$id');
      if (res.statusCode == 200) {
        _errorStreak = 0;
        final snap = TrackingSnapshot.fromJson(
          jsonDecode(res.body) as Map<String, dynamic>,
        );
        emit(TrackingReady(snap));
        if (snap.status.isTerminal) {
          _stop();
          await SecureStore.clearActiveRequestId();
        }
      } else if (res.statusCode == 404) {
        // Anti-enumeration 404: the contract doesn't say this clears the active
        // id, so keep it and surface honestly.
        _stop();
        if (state is! TrackingReady) {
          emit(
            const TrackingUnavailable(
              'We could not find this request on the server.',
              recoverable: false,
            ),
          );
        }
      } else if (res.statusCode == 401 || res.statusCode == 403) {
        _stop();
        emit(
          const TrackingUnavailable(
            'Your session expired. Sign in again.',
            recoverable: false,
          ),
        );
      } else {
        _degrade('Live status is unavailable right now.');
      }
    } catch (_) {
      _degrade('Live status is unavailable right now.');
    } finally {
      _fetching = false;
    }
  }

  void _degrade(String message) {
    _errorStreak++;
    final current = state;
    if (current is TrackingReady) {
      // Keep the last known snapshot; just mark it going stale.
      emit(TrackingReady(current.snapshot, stalePolls: _errorStreak));
      // Back off after sustained failure.
      if (_errorStreak == 3 && _timer != null) {
        _timer?.cancel();
        _timer = Timer.periodic(_interval * 3, (_) => _fetch());
      }
    } else {
      emit(TrackingUnavailable(message));
    }
  }

  void _stop() {
    _timer?.cancel();
    _timer = null;
  }

  @override
  Future<void> close() {
    _stop();
    return super.close();
  }
}
