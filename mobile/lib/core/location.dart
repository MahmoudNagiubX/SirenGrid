import 'dart:async';

import 'package:geolocator/geolocator.dart';

/// Fresh device-GPS acquisition + permission/readiness flow.
///
/// Ported from the donor branch (its typed exceptions and readiness enum are
/// sound). A request is NEVER submitted with a fabricated or `0,0` coordinate:
/// callers must handle these exceptions.
sealed class LocationFailure implements Exception {
  const LocationFailure(this.message);
  final String message;
  @override
  String toString() => message;
}

class LocationServicesDisabled extends LocationFailure {
  const LocationServicesDisabled()
    : super(
        'Location services are off. Turn on GPS to send an emergency '
        'request.',
      );
}

class LocationPermissionDenied extends LocationFailure {
  const LocationPermissionDenied()
    : super('Location permission is needed to send responders to you.');
}

class LocationPermissionPermanentlyDenied extends LocationFailure {
  const LocationPermissionPermanentlyDenied()
    : super('Location permission is blocked. Enable it in system settings.');
}

class LocationAcquisitionFailed extends LocationFailure {
  const LocationAcquisitionFailed([String? message])
    : super(message ?? 'Could not get your current location. Try again.');
}

enum LocationReadiness {
  ready,
  servicesOff,
  permissionRequired,
  permissionBlocked,
  unknown,
}

/// Injectable seam so widget/cubit tests never touch the platform.
abstract class LocationPort {
  Future<bool> isServiceEnabled();
  Future<LocationPermission> checkPermission();
  Future<LocationPermission> requestPermission();
  Future<Position> currentPosition({Duration timeLimit});
  Future<bool> openAppSettings();
  Future<bool> openLocationSettings();
}

class GeolocatorLocationPort implements LocationPort {
  const GeolocatorLocationPort();

  @override
  Future<bool> isServiceEnabled() => Geolocator.isLocationServiceEnabled();

  @override
  Future<LocationPermission> checkPermission() => Geolocator.checkPermission();

  @override
  Future<LocationPermission> requestPermission() =>
      Geolocator.requestPermission();

  @override
  Future<Position> currentPosition({
    Duration timeLimit = const Duration(seconds: 12),
  }) {
    return Geolocator.getCurrentPosition(
      locationSettings: LocationSettings(
        accuracy: LocationAccuracy.high,
        timeLimit: timeLimit,
      ),
    );
  }

  @override
  Future<bool> openAppSettings() => Geolocator.openAppSettings();

  @override
  Future<bool> openLocationSettings() => Geolocator.openLocationSettings();
}

class LocationService {
  LocationService([LocationPort? port])
    : _port = port ?? const GeolocatorLocationPort();

  final LocationPort _port;

  Future<LocationReadiness> readiness() async {
    try {
      if (!await _port.isServiceEnabled()) return LocationReadiness.servicesOff;
      final p = await _port.checkPermission();
      return switch (p) {
        LocationPermission.always ||
        LocationPermission.whileInUse => LocationReadiness.ready,
        LocationPermission.deniedForever => LocationReadiness.permissionBlocked,
        _ => LocationReadiness.permissionRequired,
      };
    } catch (_) {
      return LocationReadiness.unknown;
    }
  }

  /// Prompts for permission if not yet decided. Returns the resulting readiness.
  Future<LocationReadiness> ensurePermission() async {
    if (!await _port.isServiceEnabled()) return LocationReadiness.servicesOff;
    var p = await _port.checkPermission();
    if (p == LocationPermission.denied) {
      p = await _port.requestPermission();
    }
    return switch (p) {
      LocationPermission.always ||
      LocationPermission.whileInUse => LocationReadiness.ready,
      LocationPermission.deniedForever => LocationReadiness.permissionBlocked,
      _ => LocationReadiness.permissionRequired,
    };
  }

  /// A single fresh, high-accuracy fix. Throws a [LocationFailure] subtype.
  Future<Position> freshPosition({
    Duration timeLimit = const Duration(seconds: 12),
  }) async {
    if (!await _port.isServiceEnabled()) {
      throw const LocationServicesDisabled();
    }
    var permission = await _port.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await _port.requestPermission();
      if (permission == LocationPermission.denied) {
        throw const LocationPermissionDenied();
      }
    }
    if (permission == LocationPermission.deniedForever) {
      throw const LocationPermissionPermanentlyDenied();
    }
    try {
      return await _port.currentPosition(timeLimit: timeLimit);
    } on TimeoutException {
      throw const LocationAcquisitionFailed(
        'Getting your location timed out. Move to open sky and retry.',
      );
    } catch (e) {
      throw LocationAcquisitionFailed('Could not get your location ($e).');
    }
  }

  Future<void> openAppSettings() => _port.openAppSettings();
  Future<void> openLocationSettings() => _port.openLocationSettings();
}
