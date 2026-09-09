import 'dart:async';
import 'dart:convert';
import 'package:flutter_bloc/flutter_bloc.dart';
import '../../core/api_client.dart';
import '../../core/services.dart';

// ponytail: typed request statuses matching Master Plan §14.2 & Architecture §10
enum CitizenRequestStatus {
  received('RECEIVED'),
  underReview('UNDER_REVIEW'),
  responseAssigned('RESPONSE_ASSIGNED'),
  enRoute('EN_ROUTE'),
  arrived('ARRIVED'),
  completed('COMPLETED'),
  cancelled('CANCELLED'),
  unknown('UNKNOWN');

  final String rawValue;
  const CitizenRequestStatus(this.rawValue);

  static CitizenRequestStatus fromString(String? val) {
    if (val == null) return CitizenRequestStatus.unknown;
    final normalized = val.trim().toUpperCase();
    for (final status in CitizenRequestStatus.values) {
      if (status.rawValue == normalized) return status;
    }
    return CitizenRequestStatus.unknown;
  }

  bool get isTerminal => this == completed || this == cancelled;

  String localizedBadge(String langCode) {
    final isAr = langCode == 'ar';
    switch (this) {
      case CitizenRequestStatus.received:
        return isAr ? 'RECEIVED (قيد المراجعة)' : 'RECEIVED (Under Review)';
      case CitizenRequestStatus.underReview:
        return isAr ? 'UNDER_REVIEW (قيد المراجعة)' : 'UNDER_REVIEW (Under Review)';
      case CitizenRequestStatus.responseAssigned:
        return isAr ? 'RESPONSE_ASSIGNED (تم توجيه المستجيب)' : 'RESPONSE_ASSIGNED (Assigned)';
      case CitizenRequestStatus.enRoute:
        return isAr ? 'EN_ROUTE (في الطريق)' : 'EN_ROUTE (En Route)';
      case CitizenRequestStatus.arrived:
        return isAr ? 'ARRIVED (وصل المستجيب)' : 'ARRIVED (Arrived)';
      case CitizenRequestStatus.completed:
        return isAr ? 'COMPLETED (اكتمل البلاغ)' : 'COMPLETED (Completed)';
      case CitizenRequestStatus.cancelled:
        return isAr ? 'CANCELLED (تم الإلغاء)' : 'CANCELLED (Cancelled)';
      case CitizenRequestStatus.unknown:
        return rawValue;
    }
  }
}

class ResponderLocation {
  final double lat;
  final double lon;

  const ResponderLocation({required this.lat, required this.lon});

  factory ResponderLocation.fromJson(Map<String, dynamic> json) {
    final lat = (json['lat'] as num?)?.toDouble() ?? 0.0;
    final lon = (json['lon'] as num?)?.toDouble() ?? 0.0;
    return ResponderLocation(lat: lat, lon: lon);
  }
}

class ResponderData {
  final String? label;
  final ResponderLocation? location;
  final String? lastUpdated;
  final String? dataReality;

  const ResponderData({
    this.label,
    this.location,
    this.lastUpdated,
    this.dataReality,
  });

  factory ResponderData.fromJson(Map<String, dynamic> json) {
    ResponderLocation? loc;
    if (json['location'] is Map<String, dynamic>) {
      loc = ResponderLocation.fromJson(json['location'] as Map<String, dynamic>);
    }
    return ResponderData(
      label: json['label']?.toString(),
      location: loc,
      lastUpdated: json['last_updated']?.toString(),
      dataReality: json['data_reality']?.toString(),
    );
  }
}

class TrackingData {
  final String requestId;
  final String? incidentId;
  final CitizenRequestStatus status;
  final String rawStatus;
  final String service;
  final int? etaSeconds;
  final ResponderData? responder;
  final String? lastUpdated;
  final String? dataReality;

  const TrackingData({
    required this.requestId,
    this.incidentId,
    required this.status,
    required this.rawStatus,
    required this.service,
    this.etaSeconds,
    this.responder,
    this.lastUpdated,
    this.dataReality,
  });

  // Derived helpers for UI presentation
  int? get etaMinutes => etaSeconds != null ? (etaSeconds! / 60).round() : null;
  double? get responderLat => responder?.location?.lat;
  double? get responderLon => responder?.location?.lon;

  // Authoritative provenance detection
  bool get isRequestSimulated => dataReality?.trim().toUpperCase() == 'SIMULATED';
  bool get isRequestSynthetic => dataReality?.trim().toUpperCase() == 'SYNTHETIC';
  bool get hasRequestProvenance => isRequestSimulated || isRequestSynthetic;

  bool get isResponderSimulated => responder?.dataReality?.trim().toUpperCase() == 'SIMULATED';
  bool get isResponderSynthetic => responder?.dataReality?.trim().toUpperCase() == 'SYNTHETIC';
  bool get hasResponderProvenance => isResponderSimulated || isResponderSynthetic;

  factory TrackingData.fromJson(Map<String, dynamic> json) {
    final rawStatus = json['status']?.toString() ?? '';
    ResponderData? responder;
    if (json['responder'] is Map<String, dynamic>) {
      responder = ResponderData.fromJson(json['responder'] as Map<String, dynamic>);
    }

    return TrackingData(
      requestId: json['request_id']?.toString() ?? '',
      incidentId: json['incident_id']?.toString(),
      status: CitizenRequestStatus.fromString(rawStatus),
      rawStatus: rawStatus,
      service: json['service']?.toString() ?? json['service_type']?.toString() ?? '',
      etaSeconds: json['eta_seconds'] as int?,
      responder: responder,
      lastUpdated: json['last_updated']?.toString(),
      dataReality: json['data_reality']?.toString(),
    );
  }
}

abstract class TrackingState {}
class TrackingInitial extends TrackingState {}
class TrackingLoading extends TrackingState {}
class TrackingActive extends TrackingState {
  final TrackingData data;
  TrackingActive(this.data);
}
class TrackingError extends TrackingState {
  final String message;
  TrackingError(this.message);
}

class TrackingCubit extends Cubit<TrackingState> {
  final ApiClient _apiClient;
  Timer? _pollingTimer;
  bool _isFetching = false;
  String? _currentTrackingId;

  // Foreground polling default: 4s (within 3–5s spec from Technical Architecture §8)
  static const Duration defaultPollInterval = Duration(seconds: 4);
  final Duration pollInterval;

  TrackingCubit(this._apiClient, {this.pollInterval = defaultPollInterval}) : super(TrackingInitial());

  String? get currentTrackingId => _currentTrackingId;

  Future<void> startTracking(String? initialRequestId) async {
    final id = initialRequestId ?? await StorageService.getActiveRequestId();
    if (id == null || id.isEmpty) {
      _stopPolling();
      _currentTrackingId = null;
      emit(TrackingInitial());
      return;
    }

    _currentTrackingId = id;
    if (state is! TrackingActive) {
      emit(TrackingLoading());
    }
    _stopPolling();

    // 1. Initial immediate fetch
    await _fetchStatus(id);

    // 2. Poll every 4 seconds if not terminal
    if (state is TrackingActive && (state as TrackingActive).data.status.isTerminal) {
      return;
    }

    _pollingTimer = Timer.periodic(pollInterval, (_) async {
      if (_currentTrackingId != null) {
        await _fetchStatus(_currentTrackingId!);
      }
    });
  }

  Future<void> refreshActiveRequest() async {
    final id = _currentTrackingId ?? await StorageService.getActiveRequestId();
    if (id != null && id.isNotEmpty) {
      await _fetchStatus(id);
    }
  }

  Future<void> clearTracking() async {
    _stopPolling();
    _currentTrackingId = null;
    await StorageService.clearActiveRequestId();
    emit(TrackingInitial());
  }

  Future<void> _fetchStatus(String id) async {
    if (_isFetching) return;
    _isFetching = true;
    try {
      final res = await _apiClient.get('/api/v1/mobile/emergency-requests/$id');
      if (res.statusCode == 200) {
        final data = TrackingData.fromJson(jsonDecode(res.body));
        emit(TrackingActive(data));

        if (data.status.isTerminal) {
          _stopPolling();
          await StorageService.clearActiveRequestId();
        }
      } else if (res.statusCode == 404) {
        // Contract semantics do not explicitly specify 404 clears active request ID.
        // Preserve stored active request ID and report failure truthfully (Correction 3).
        _stopPolling();
        if (state is! TrackingActive) {
          emit(TrackingError('Emergency request not found on server.'));
        }
      } else if (res.statusCode == 401 || res.statusCode == 403) {
        _stopPolling();
        emit(TrackingError('Session expired. Please sign in again.'));
      } else {
        if (state is! TrackingActive) {
          emit(TrackingError('Live status currently unavailable. Please verify network connection.'));
        }
      }
    } catch (e) {
      if (state is! TrackingActive) {
        emit(TrackingError('Live status currently unavailable. Please verify network connection.'));
      }
    } finally {
      _isFetching = false;
    }
  }

  void _stopPolling() {
    _pollingTimer?.cancel();
    _pollingTimer = null;
  }

  @override
  Future<void> close() {
    _stopPolling();
    return super.close();
  }
}
