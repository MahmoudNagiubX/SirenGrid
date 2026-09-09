import 'dart:ui' as ui;
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import '../services.dart';

enum AppLanguageOption {
  system,
  ar,
  en,
}

class AppLocale extends Locale {
  final AppLanguageOption option;

  const AppLocale(super.languageCode, this.option);

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is AppLocale &&
          runtimeType == other.runtimeType &&
          languageCode == other.languageCode &&
          option == other.option;

  @override
  int get hashCode => languageCode.hashCode ^ option.hashCode;
}

/// Manages application locale state.
/// Defaults to operating system / device locale (Arabic if begins with 'ar', otherwise English).
/// Persists explicit user selections across launches.
class LocaleCubit extends Cubit<Locale> {
  static Locale? overridePlatformLocale;

  LocaleCubit([Locale? initialLocale, AppLanguageOption? initialOption])
      : super(_initial(initialLocale, initialOption)) {
    _loadPreference();
  }

  static AppLocale _initial([Locale? initialLocale, AppLanguageOption? initialOption]) {
    if (initialOption != null && initialLocale != null) {
      return AppLocale(initialLocale.languageCode, initialOption);
    }
    if (initialLocale != null) {
      return AppLocale(
        initialLocale.languageCode,
        initialLocale.languageCode == 'ar' ? AppLanguageOption.ar : AppLanguageOption.en,
      );
    }
    final devLocale = resolveDeviceLocale();
    return AppLocale(devLocale.languageCode, AppLanguageOption.system);
  }

  static Locale resolveDeviceLocale([Locale? platformLocale]) {
    final loc = platformLocale ?? overridePlatformLocale ?? ui.PlatformDispatcher.instance.locale;
    if (loc.languageCode.toLowerCase().startsWith('ar')) {
      return const Locale('ar');
    }
    return const Locale('en');
  }

  Future<void> _loadPreference() async {
    final pref = await StorageService.getLanguagePreference();
    if (pref == 'ar') {
      emit(const AppLocale('ar', AppLanguageOption.ar));
    } else if (pref == 'en') {
      emit(const AppLocale('en', AppLanguageOption.en));
    } else if (pref == 'system') {
      final dev = resolveDeviceLocale();
      emit(AppLocale(dev.languageCode, AppLanguageOption.system));
    }
  }

  Future<void> setLanguageOption(AppLanguageOption option) async {
    final Locale resolved;
    switch (option) {
      case AppLanguageOption.system:
        resolved = resolveDeviceLocale();
        break;
      case AppLanguageOption.ar:
        resolved = const Locale('ar');
        break;
      case AppLanguageOption.en:
        resolved = const Locale('en');
        break;
    }
    emit(AppLocale(resolved.languageCode, option));
    await StorageService.saveLanguagePreference(
      option == AppLanguageOption.system
          ? 'system'
          : (option == AppLanguageOption.ar ? 'ar' : 'en'),
    );
  }

  void setLocale(Locale locale) {
    if (locale.languageCode == 'ar') {
      setLanguageOption(AppLanguageOption.ar);
    } else {
      setLanguageOption(AppLanguageOption.en);
    }
  }

  void toggleLocale() {
    if (isArabic) {
      setLanguageOption(AppLanguageOption.en);
    } else {
      setLanguageOption(AppLanguageOption.ar);
    }
  }

  bool get isArabic => state.languageCode == 'ar';

  AppLanguageOption get currentOption {
    final s = state;
    if (s is AppLocale) return s.option;
    return s.languageCode == 'ar' ? AppLanguageOption.ar : AppLanguageOption.en;
  }
}
