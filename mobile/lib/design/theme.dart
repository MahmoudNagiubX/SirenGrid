import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import 'tokens.dart';

/// The single app theme. Rubik across EN + AR (brief §7/§8) via `google_fonts`
/// (cached after first fetch; no local binaries were supplied to the handoff).
ThemeData sgTheme() {
  final base = ThemeData(
    useMaterial3: true,
    brightness: Brightness.light,
    scaffoldBackgroundColor: SgColors.bgApp,
    colorScheme: const ColorScheme.light(
      primary: SgColors.navy900,
      onPrimary: Colors.white,
      secondary: SgColors.blue600,
      onSecondary: Colors.white,
      error: SgColors.emergency,
      onError: Colors.white,
      surface: SgColors.bgSurface,
      onSurface: SgColors.textPrimary,
    ),
    splashFactory: InkRipple.splashFactory,
  );

  final textTheme = GoogleFonts.rubikTextTheme(base.textTheme)
      .apply(bodyColor: SgColors.textPrimary, displayColor: SgColors.heading);

  return base.copyWith(
    textTheme: textTheme,
    primaryTextTheme: textTheme,
    appBarTheme: const AppBarTheme(
      backgroundColor: SgColors.bgApp,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      centerTitle: false,
    ),
    dividerTheme: const DividerThemeData(
      color: SgColors.borderHairline,
      thickness: 1,
      space: 1,
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      backgroundColor: SgColors.navy950,
      contentTextStyle: GoogleFonts.rubik(color: Colors.white, fontSize: 14),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(SgRadius.control),
      ),
    ),
  );
}
