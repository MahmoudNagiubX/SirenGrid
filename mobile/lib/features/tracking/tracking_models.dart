import 'package:latlong2/latlong.dart';

/// Typed, float-safe projection of the current backend
/// `GET /api/v1/mobile/emergency-requests/{id}` response
/// (`MobileEmergencyTrackingRead` on `origin/main`, including the
/// responder-tracking additions: `tracking_available`, `emergency_location`,
/// `route`, `responder.operational_status`).
///
/// Every numeric field is parsed through `num` then `.toDouble()` (Codex P0-04).
/// Unknown / missing optional fields never throw.

double? _numOrNull(dynamic v) => (v is num) ? v.toDouble() : null;

LatLng? _coord(dynamic v) {
  if (v is! Map) return null;
  final lat = _numOrNull(v['lat']);
  final lon = _numOrNull(v['lon']);
  if (lat == null || lon == null) return null;
  if (lat.isNaN || lon.isNaN || lat.abs() > 90 || lon.abs() > 180) return null;
  return LatLng(lat, lon);
}

enum CitizenRequestStatus {
  received('RECEIVED'),
  underReview('UNDER_REVIEW'),
  responseAssigned('RESPONSE_ASSIGNED'),
  enRoute('EN_ROUTE'),
  arrived('ARRIVED'),
  completed('COMPLETED'),
  cancelled('CANCELLED'),
  unknown('UNKNOWN');

  const CitizenRequestStatus(this.raw);
  final String raw;

  static CitizenRequestStatus parse(String? v) {
    final u = (v ?? '').trim().toUpperCase();
    return CitizenRequestStatus.values.firstWhere(
      (s) => s.raw == u,
      orElse: () => CitizenRequestStatus.unknown,
    );
  }

  bool get isTerminal => this == completed || this == cancelled;

  /// 0..3 index into the Received/Assigned/En route/Arrived timeline.
  int get timelineStep => switch (this) {
    received || underReview || unknown => 0,
    responseAssigned => 1,
    enRoute => 2,
    arrived || completed => 3,
    cancelled => 0,
  };
}

enum DataReality {
  realPublic,
  realLive,
  realDerived,
  simulated,
  synthetic,
  unknown,
}

DataReality _dataReality(String? v) => switch ((v ?? '').trim().toUpperCase()) {
  'REAL_PUBLIC' => DataReality.realPublic,
  'REAL_LIVE' => DataReality.realLive,
  'REAL_DERIVED' => DataReality.realDerived,
  'SIMULATED' => DataReality.simulated,
  'SYNTHETIC' => DataReality.synthetic,
  _ => DataReality.unknown,
};

enum FreshnessStatus { live, fresh, stale, static_, unknown }

FreshnessStatus _freshness(String? v) =>
    switch ((v ?? '').trim().toUpperCase()) {
      'LIVE' => FreshnessStatus.live,
      'FRESH' => FreshnessStatus.fresh,
      'STALE' => FreshnessStatus.stale,
      'STATIC' => FreshnessStatus.static_,
      _ => FreshnessStatus.unknown,
    };

class ResponderView {
  const ResponderView({
    required this.id,
    required this.label,
    required this.location,
    required this.lastUpdated,
    required this.freshnessStatus,
    required this.dataReality,
    required this.operationalStatus,
  });

  final String id;
  final String label;
  final LatLng? location;
  final DateTime? lastUpdated;
  final FreshnessStatus freshnessStatus;
  final DataReality dataReality;
  final String? operationalStatus;

  bool get isSimulated =>
      dataReality == DataReality.simulated ||
      dataReality == DataReality.synthetic;

  bool get isLive => dataReality == DataReality.realLive;

  bool get isStale => freshnessStatus == FreshnessStatus.stale;

  factory ResponderView.fromJson(Map<String, dynamic> j) => ResponderView(
    id: j['id']?.toString() ?? '',
    label: j['label']?.toString() ?? '',
    location: _coord(j['location']),
    lastUpdated: DateTime.tryParse(j['last_updated']?.toString() ?? '')
        ?.toLocal(),
    freshnessStatus: _freshness(j['freshness_status']?.toString()),
    dataReality: _dataReality(j['data_reality']?.toString()),
    operationalStatus: j['operational_status']?.toString(),
  );
}

class RouteView {
  const RouteView({
    required this.polyline,
    required this.remainingEtaSeconds,
    required this.progressFraction,
    required this.dataReality,
    required this.trackingSource,
  });

  /// GeoJSON `[lon, lat]` order converted to `LatLng`. May be empty if geometry
  /// was malformed (never fabricated).
  final List<LatLng> polyline;
  final double? remainingEtaSeconds;
  final double progressFraction;
  final DataReality dataReality;
  final String trackingSource;

  bool get isSimulatedProjection =>
      trackingSource.toUpperCase() == 'SIMULATED_ROUTE_PROJECTION' ||
      dataReality == DataReality.simulated;

  static List<LatLng> _lineString(dynamic geometry) {
    if (geometry is! Map) return const [];
    if ((geometry['type']?.toString() ?? '') != 'LineString') return const [];
    final coords = geometry['coordinates'];
    if (coords is! List) return const [];
    final out = <LatLng>[];
    for (final pair in coords) {
      if (pair is! List || pair.length < 2) return const [];
      final lon = _numOrNull(pair[0]);
      final lat = _numOrNull(pair[1]);
      if (lon == null || lat == null) return const [];
      if (lat.isNaN || lon.isNaN || lat.abs() > 90 || lon.abs() > 180) {
        return const [];
      }
      out.add(LatLng(lat, lon));
    }
    return out.length >= 2 ? out : const [];
  }

  factory RouteView.fromJson(Map<String, dynamic> j) => RouteView(
    polyline: _lineString(j['geometry']),
    remainingEtaSeconds: _numOrNull(j['remaining_eta_seconds']),
    progressFraction: (_numOrNull(j['progress_fraction']) ?? 0).clamp(0, 1),
    dataReality: _dataReality(j['data_reality']?.toString()),
    trackingSource: j['tracking_source']?.toString() ?? '',
  );
}

class TrackingSnapshot {
  const TrackingSnapshot({
    required this.requestId,
    required this.incidentId,
    required this.serviceCode,
    required this.status,
    required this.rawStatus,
    required this.etaSeconds,
    required this.responder,
    required this.emergencyLocation,
    required this.route,
    required this.lastUpdated,
    required this.trackingAvailable,
  });

  final String requestId;
  final String? incidentId;
  final String serviceCode; // AMBULANCE / FIRE / POLICE / GENERAL
  final CitizenRequestStatus status;
  final String rawStatus;
  final double? etaSeconds;
  final ResponderView? responder;
  final LatLng? emergencyLocation;
  final RouteView? route;
  final DateTime? lastUpdated;
  final bool trackingAvailable;

  /// The ETA to show — prefer the live remaining-ETA from the route projection,
  /// fall back to the canonical top-level `eta_seconds`. Backend-owned only.
  double? get effectiveEtaSeconds => route?.remainingEtaSeconds ?? etaSeconds;

  int? get etaMinutes {
    final s = effectiveEtaSeconds;
    if (s == null) return null;
    return (s / 60).ceil().clamp(0, 999);
  }

  bool get hasResponderLocation => responder?.location != null;

  bool get isSimulated =>
      (responder?.isSimulated ?? false) ||
      (route?.isSimulatedProjection ?? false);

  bool get isStale => responder?.isStale ?? false;

  factory TrackingSnapshot.fromJson(Map<String, dynamic> j) {
    final responderJson = j['responder'];
    final routeJson = j['route'];
    return TrackingSnapshot(
      requestId: j['request_id']?.toString() ?? '',
      incidentId: j['incident_id']?.toString(),
      serviceCode: (j['service']?.toString() ?? 'GENERAL').toUpperCase(),
      status: CitizenRequestStatus.parse(j['status']?.toString()),
      rawStatus: j['status']?.toString() ?? '',
      etaSeconds: _numOrNull(j['eta_seconds']),
      responder: responderJson is Map<String, dynamic>
          ? ResponderView.fromJson(responderJson)
          : null,
      emergencyLocation: _coord(j['emergency_location']),
      route: routeJson is Map<String, dynamic>
          ? RouteView.fromJson(routeJson)
          : null,
      lastUpdated: DateTime.tryParse(j['last_updated']?.toString() ?? '')
          ?.toLocal(),
      trackingAvailable: j['tracking_available'] == true,
    );
  }
}
