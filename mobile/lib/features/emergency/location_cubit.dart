import 'package:flutter_bloc/flutter_bloc.dart';

import '../../core/location.dart';

/// Drives the Home screen's current-location readiness card. It only checks /
/// requests permission and readiness — the actual fresh fix for a submission is
/// acquired at submit time by [HomeCubit] (brief §3 confirmation flow).
class LocationCubit extends Cubit<LocationReadiness> {
  LocationCubit(this._service) : super(LocationReadiness.unknown);

  final LocationService _service;

  Future<void> refresh() async {
    emit(await _service.readiness());
  }

  Future<void> requestPermission() async {
    emit(await _service.ensurePermission());
  }

  Future<void> openLocationSettings() async {
    await _service.openLocationSettings();
  }

  Future<void> openAppSettings() async {
    await _service.openAppSettings();
  }
}
