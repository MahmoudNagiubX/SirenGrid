import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'app_strings.dart';

class SirenLocalizations {
  final Locale locale;

  SirenLocalizations(this.locale);

  static SirenLocalizations of(BuildContext context) {
    return Localizations.of<SirenLocalizations>(context, SirenLocalizations) ??
        SirenLocalizations(const Locale('ar'));
  }

  static const LocalizationsDelegate<SirenLocalizations> delegate =
      _SirenLocalizationsDelegate();

  String translate(String key) {
    return AppStrings.get(key, locale.languageCode);
  }

  bool get isRtl => locale.languageCode == 'ar';
}

class _SirenLocalizationsDelegate
    extends LocalizationsDelegate<SirenLocalizations> {
  const _SirenLocalizationsDelegate();

  @override
  bool isSupported(Locale locale) => ['ar', 'en'].contains(locale.languageCode);

  @override
  Future<SirenLocalizations> load(Locale locale) {
    return SynchronousFuture<SirenLocalizations>(SirenLocalizations(locale));
  }

  @override
  bool shouldReload(_SirenLocalizationsDelegate old) => false;
}

extension SirenLocalizationExtension on BuildContext {
  String tr(String key) => SirenLocalizations.of(this).translate(key);
}
