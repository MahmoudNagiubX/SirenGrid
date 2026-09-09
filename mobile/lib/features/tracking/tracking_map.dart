import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

import '../../design/components/sg_markers.dart';
import '../../design/tokens.dart';
import 'tracking_models.dart';

/// Real interactive basemap for Live Response Tracking (brief §13/§14).
///
/// A real OSM raster basemap toned toward the cool blue-gray SirenGrid map
/// palette (no API key, no new provider — same approach as the Command Center
/// web map). Citizen pin = flat red dot at `emergency_location`; responder =
/// navy circle + service glyph at `responder.location`; approved route drawn as
/// white casing → blue halo → strong route line. The responder marker is
/// interpolated between successive backend snapshots for smoothness — visual
/// only; each new snapshot reconciles it and it never moves after updates stop.
class TrackingMap extends StatefulWidget {
  const TrackingMap({
    super.key,
    required this.snapshot,
    required this.serviceIcon,
  });

  final TrackingSnapshot snapshot;
  final String serviceIcon;

  @override
  State<TrackingMap> createState() => TrackingMapState();
}

class TrackingMapState extends State<TrackingMap>
    with SingleTickerProviderStateMixin {
  final _map = MapController();
  late final AnimationController _lerp = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 900),
  );

  LatLng? _displayedResponder;
  LatLng? _fromResponder;
  LatLng? _toResponder;
  bool _userMovedMap = false;

  @override
  void initState() {
    super.initState();
    _displayedResponder = widget.snapshot.responder?.location;
    _toResponder = _displayedResponder;
    _lerp.addListener(() {
      if (_fromResponder == null || _toResponder == null) return;
      setState(() {
        _displayedResponder = _lerpLatLng(
          _fromResponder!,
          _toResponder!,
          _lerp.value,
        );
      });
    });
    WidgetsBinding.instance.addPostFrameCallback((_) => _fitBounds());
  }

  @override
  void didUpdateWidget(covariant TrackingMap oldWidget) {
    super.didUpdateWidget(oldWidget);
    final next = widget.snapshot.responder?.location;
    if (next != null && next != _toResponder) {
      _fromResponder = _displayedResponder ?? next;
      _toResponder = next;
      _lerp
        ..reset()
        ..forward();
    } else if (next == null) {
      _displayedResponder = null;
      _toResponder = null;
    }
    if (!_userMovedMap) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _fitBounds());
    }
  }

  @override
  void dispose() {
    _lerp.dispose();
    _map.dispose();
    super.dispose();
  }

  List<LatLng> get _focusPoints {
    final pts = <LatLng>[];
    final s = widget.snapshot;
    if (s.emergencyLocation != null) pts.add(s.emergencyLocation!);
    if (_displayedResponder != null) pts.add(_displayedResponder!);
    if (s.route != null) pts.addAll(s.route!.polyline);
    return pts;
  }

  void _fitBounds() {
    final pts = _focusPoints;
    if (!mounted || pts.isEmpty) return;
    if (pts.length == 1) {
      _map.move(pts.first, 15);
      return;
    }
    _map.fitCamera(
      CameraFit.bounds(
        bounds: LatLngBounds.fromPoints(pts),
        padding: const EdgeInsets.fromLTRB(48, 190, 48, 260),
        maxZoom: 16.5,
      ),
    );
  }

  /// Public: re-center the map on the current focus (recenter FAB).
  void recenter() {
    _userMovedMap = false;
    _fitBounds();
  }

  @override
  Widget build(BuildContext context) {
    final s = widget.snapshot;
    final route = s.route?.polyline ?? const <LatLng>[];
    final center =
        s.emergencyLocation ??
        _displayedResponder ??
        (route.isNotEmpty ? route.first : const LatLng(30.0561, 31.3452));

    return FlutterMap(
      mapController: _map,
      options: MapOptions(
        initialCenter: center,
        initialZoom: 14,
        minZoom: 3,
        maxZoom: 18,
        backgroundColor: SgColors.mapBg,
        interactionOptions: const InteractionOptions(
          flags:
              InteractiveFlag.pinchZoom |
              InteractiveFlag.drag |
              InteractiveFlag.doubleTapZoom |
              InteractiveFlag.flingAnimation,
        ),
        onPositionChanged: (pos, hasGesture) {
          if (hasGesture) _userMovedMap = true;
        },
      ),
      children: [
        ColorFiltered(
          colorFilter: const ColorFilter.matrix(_coolDesaturate),
          child: TileLayer(
            urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
            userAgentPackageName: 'eg.sirengrid.sirengrid_citizen',
            tileProvider: NetworkTileProvider(),
            maxNativeZoom: 19,
          ),
        ),
        if (route.length >= 2) ...[
          PolylineLayer(
            polylines: [
              Polyline(points: route, strokeWidth: 13, color: Colors.white),
            ],
          ),
          PolylineLayer(
            polylines: [
              Polyline(
                points: route,
                strokeWidth: 9,
                color: SgColors.mapRouteHalo,
              ),
            ],
          ),
          PolylineLayer(
            polylines: [
              Polyline(points: route, strokeWidth: 5, color: SgColors.mapRoute),
            ],
          ),
        ],
        MarkerLayer(
          markers: [
            if (s.emergencyLocation != null)
              Marker(
                point: s.emergencyLocation!,
                width: SgMapPin.size.width,
                height: SgMapPin.size.height,
                alignment: Alignment.bottomCenter,
                child: const SgMapPin(label: 'You are here'),
              ),
            if (_displayedResponder != null)
              Marker(
                point: _displayedResponder!,
                width: SgResponderMarker.size.width,
                height: SgResponderMarker.size.height,
                alignment: Alignment.center,
                child: SgResponderMarker(
                  icon: widget.serviceIcon,
                  selected: true,
                  headingDegrees: _headingToEmergency(),
                ),
              ),
          ],
        ),
      ],
    );
  }

  double? _headingToEmergency() {
    final r = _displayedResponder;
    final e = widget.snapshot.emergencyLocation;
    if (r == null || e == null) return null;
    final dLon = (e.longitude - r.longitude) * math.pi / 180;
    final lat1 = r.latitude * math.pi / 180;
    final lat2 = e.latitude * math.pi / 180;
    final y = math.sin(dLon) * math.cos(lat2);
    final x =
        math.cos(lat1) * math.sin(lat2) -
        math.sin(lat1) * math.cos(lat2) * math.cos(dLon);
    final bearing = math.atan2(y, x) * 180 / math.pi;
    return (bearing + 360) % 360;
  }

  static LatLng _lerpLatLng(LatLng a, LatLng b, double t) => LatLng(
    a.latitude + (b.latitude - a.latitude) * t,
    a.longitude + (b.longitude - a.longitude) * t,
  );

  // Cool, light, slightly desaturated tone toward the map palette (brief §13).
  static const List<double> _coolDesaturate = <double>[
    0.72, 0.20, 0.02, 0, 8, //
    0.06, 0.80, 0.06, 0, 12, //
    0.10, 0.16, 0.80, 0, 20, //
    0, 0, 0, 1, 0, //
  ];
}
