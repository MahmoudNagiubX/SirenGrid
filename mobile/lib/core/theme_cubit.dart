import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'services.dart';

/// Manages application ThemeMode (light or dark).
/// Persists user selection via StorageService.
class ThemeCubit extends Cubit<ThemeMode> {
  ThemeCubit([super.initial = ThemeMode.light]) {
    _loadPreference();
  }

  Future<void> _loadPreference() async {
    final pref = await StorageService.getThemePreference();
    if (pref == 'dark') {
      emit(ThemeMode.dark);
    } else if (pref == 'light') {
      emit(ThemeMode.light);
    }
  }

  Future<void> setThemeMode(ThemeMode mode) async {
    emit(mode);
    await StorageService.saveThemePreference(mode == ThemeMode.dark ? 'dark' : 'light');
  }

  bool get isDark => state == ThemeMode.dark;
}
