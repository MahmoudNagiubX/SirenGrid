import 'package:flutter/material.dart';

/// SirenGrid Canonical Design Tokens
/// Derived strictly from the locked Arabic prototype reference
class AppColors {
  // Brand Navy Spectrum (Distinct Canonical Shades)
  static const Color primary = Color(0xFF395886); // Action CTA brand navy
  static const Color primaryDark = Color(0xFF2E476C); // Active/pressed primary
  static const Color primarySubtle = Color(0xFFEDF2F7); // Subtle circle/radar
  static const Color textDark = Color(0xFF181D28); // Headings, titles, labels
  static const Color avatarNavy = Color(0xFF253858); // Avatar circle background
  static const Color accentBlue = Color(0xFF2563EB); // Nav & interactive links
  static const Color accentBlueLight = Color(0xFFEBF4FE); // Pill background

  // Emergency Semantic Spectrum
  static const Color emergency = Color(0xFFEF233C); // Primary medical red
  static const Color emergencyStrong = Color(0xFFD90429); // Confirm button red
  static const Color emergencyLight = Color(0xFFFFF1F2); // Subtle alert bg
  static const Color emergencyBorder = Color(0xFFF7BFC6); // Alert border

  // Service-Specific Semantic Palette
  // Ambulance
  static const Color ambulanceFrom = Color(0xFFEF233C);
  static const Color ambulanceTo = Color(0xFFD90429);
  static const Color ambulanceBg = Color(0xFFFFF1F2);

  // Fire
  static const Color fireFrom = Color(0xFFFB923C);
  static const Color fireTo = Color(0xFFEA580C);
  static const Color fireBg = Color(0xFFFFF7ED);

  // Police
  static const Color policeFrom = Color(0xFF3B82F6);
  static const Color policeTo = Color(0xFF1D4ED8);
  static const Color policeBg = Color(0xFFEFF6FF);

  // General Emergency
  static const Color generalFrom = Color(0xFF14B8A6);
  static const Color generalTo = Color(0xFF0F766E);
  static const Color generalBg = Color(0xFFF0FDFA);

  // Neutrals & Surfaces
  static const Color background = Color(0xFFF7FBFA); // Canonical page bg
  static const Color surface = Color(0xFFFFFFFF); // Card & sheet surface
  static const Color border = Color(0xFFE2E8F0); // Card & input border
  static const Color borderLight = Color(0xFFE8EFF5); // Divider line

  // Text Typography Colors
  static const Color textPrimary = Color(0xFF181D28);
  static const Color textMuted = Color(0xFF64748B);
  static const Color textSubtle = Color(0xFF94A3B8);

  // Verification & Status Indicators
  static const Color statusVerifiedText = Color(0xFF059669);
  static const Color statusVerifiedBg = Color(0xFFE8FBF4);
  static const Color statusVerifiedBorder = Color(0xFFA7F3D0);

  // Backward-compatibility aliases for existing code
  static const Color primaryNavy = primary;
  static const Color calmTeal = generalFrom;
  static const Color emergencyRed = emergencyStrong;
  static const Color cardBg = surface;
  static const Color textSecondary = textMuted;
}

class AppRadii {
  static const double card = 16.0;
  static const double cardLarge = 24.0;
  static const double sheet = 28.0;
  static const double button = 12.0;
  static const double input = 12.0;
  static const double pill = 9999.0;
}

class AppDimensions {
  static const double buttonHeight = 48.0;
  static const double inputHeight = 48.0;
  static const double maxViewportWidth = 430.0;
}

class AppThemeColors extends ThemeExtension<AppThemeColors> {
  final Color background;
  final Color surface;
  final Color surfaceElevated;
  final Color border;
  final Color borderLight;
  final Color textPrimary;
  final Color textMuted;
  final Color textSubtle;
  final Color accentBlueLight;
  final Color inputFill;
  final Color neutralCard;
  final Color mapPlaceholderBg;

  const AppThemeColors({
    required this.background,
    required this.surface,
    required this.surfaceElevated,
    required this.border,
    required this.borderLight,
    required this.textPrimary,
    required this.textMuted,
    required this.textSubtle,
    required this.accentBlueLight,
    required this.inputFill,
    required this.neutralCard,
    required this.mapPlaceholderBg,
  });

  static const light = AppThemeColors(
    background: Color(0xFFF7FBFA),
    surface: Color(0xFFFFFFFF),
    surfaceElevated: Color(0xFFF8FAFC),
    border: Color(0xFFE2E8F0),
    borderLight: Color(0xFFE8EFF5),
    textPrimary: Color(0xFF181D28),
    textMuted: Color(0xFF64748B),
    textSubtle: Color(0xFF94A3B8),
    accentBlueLight: Color(0xFFEBF4FE),
    inputFill: Color(0xFFFFFFFF),
    neutralCard: Color(0xFFF1F5F9),
    mapPlaceholderBg: Color(0xFFE2E8F0),
  );

  static const dark = AppThemeColors(
    background: Color(0xFF0B1120), // Dark navy
    surface: Color(0xFF1E293B), // Slate / lighter navy
    surfaceElevated: Color(0xFF24334A),
    border: Color(0xFF334155), // Subtle low-contrast blue-gray
    borderLight: Color(0xFF1E293B),
    textPrimary: Color(0xFFF8FAFC), // Near-white
    textMuted: Color(0xFF94A3B8), // Muted cool gray
    textSubtle: Color(0xFF64748B),
    accentBlueLight: Color(0x332563EB), // Dark blue pill
    inputFill: Color(0xFF131D2E),
    neutralCard: Color(0xFF151F30),
    mapPlaceholderBg: Color(0xFF151F30),
  );

  @override
  ThemeExtension<AppThemeColors> copyWith({
    Color? background,
    Color? surface,
    Color? surfaceElevated,
    Color? border,
    Color? borderLight,
    Color? textPrimary,
    Color? textMuted,
    Color? textSubtle,
    Color? accentBlueLight,
    Color? inputFill,
    Color? neutralCard,
    Color? mapPlaceholderBg,
  }) {
    return AppThemeColors(
      background: background ?? this.background,
      surface: surface ?? this.surface,
      surfaceElevated: surfaceElevated ?? this.surfaceElevated,
      border: border ?? this.border,
      borderLight: borderLight ?? this.borderLight,
      textPrimary: textPrimary ?? this.textPrimary,
      textMuted: textMuted ?? this.textMuted,
      textSubtle: textSubtle ?? this.textSubtle,
      accentBlueLight: accentBlueLight ?? this.accentBlueLight,
      inputFill: inputFill ?? this.inputFill,
      neutralCard: neutralCard ?? this.neutralCard,
      mapPlaceholderBg: mapPlaceholderBg ?? this.mapPlaceholderBg,
    );
  }

  @override
  ThemeExtension<AppThemeColors> lerp(ThemeExtension<AppThemeColors>? other, double t) {
    if (other is! AppThemeColors) return this;
    return AppThemeColors(
      background: Color.lerp(background, other.background, t)!,
      surface: Color.lerp(surface, other.surface, t)!,
      surfaceElevated: Color.lerp(surfaceElevated, other.surfaceElevated, t)!,
      border: Color.lerp(border, other.border, t)!,
      borderLight: Color.lerp(borderLight, other.borderLight, t)!,
      textPrimary: Color.lerp(textPrimary, other.textPrimary, t)!,
      textMuted: Color.lerp(textMuted, other.textMuted, t)!,
      textSubtle: Color.lerp(textSubtle, other.textSubtle, t)!,
      accentBlueLight: Color.lerp(accentBlueLight, other.accentBlueLight, t)!,
      inputFill: Color.lerp(inputFill, other.inputFill, t)!,
      neutralCard: Color.lerp(neutralCard, other.neutralCard, t)!,
      mapPlaceholderBg: Color.lerp(mapPlaceholderBg, other.mapPlaceholderBg, t)!,
    );
  }
}

class AppTheme {
  /// Resolves ThemeData with appropriate font family and colors based on locale & theme mode.
  /// Arabic -> 'Rubik', English -> 'Lexend'
  static ThemeData themeForLocale(Locale locale, {bool isDark = false}) {
    final String fontFamily = locale.languageCode == 'ar' ? 'Rubik' : 'Lexend';
    final colors = isDark ? AppThemeColors.dark : AppThemeColors.light;

    return ThemeData(
      useMaterial3: true,
      brightness: isDark ? Brightness.dark : Brightness.light,
      fontFamily: fontFamily,
      scaffoldBackgroundColor: colors.background,
      colorScheme: isDark
          ? ColorScheme.dark(
              primary: AppColors.accentBlue,
              secondary: AppColors.accentBlue,
              surface: colors.surface,
              onSurface: colors.textPrimary,
              outline: colors.border,
              error: AppColors.emergencyStrong,
            )
          : ColorScheme.light(
              primary: AppColors.primary,
              secondary: AppColors.accentBlue,
              surface: colors.surface,
              onSurface: colors.textPrimary,
              outline: colors.border,
              error: AppColors.emergencyStrong,
            ),
      extensions: [colors],
      appBarTheme: AppBarTheme(
        backgroundColor: colors.surface,
        foregroundColor: colors.textPrimary,
        elevation: 0,
        centerTitle: false,
      ),
      cardTheme: CardThemeData(
        color: colors.surface,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppRadii.card),
          side: BorderSide(color: colors.border),
        ),
      ),
      dividerTheme: DividerThemeData(
        color: colors.border,
        thickness: 1,
        space: 1,
      ),
      bottomSheetTheme: BottomSheetThemeData(
        backgroundColor: colors.surface,
        modalBackgroundColor: colors.surface,
        shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(AppRadii.sheet)),
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          minimumSize: const Size.fromHeight(AppDimensions.buttonHeight),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AppRadii.button)),
          backgroundColor: isDark ? const Color(0xFF2563EB) : AppColors.primary,
          foregroundColor: Colors.white,
          textStyle: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
          elevation: 0,
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          minimumSize: const Size.fromHeight(AppDimensions.buttonHeight),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AppRadii.button)),
          side: BorderSide(color: colors.border),
          foregroundColor: colors.textPrimary,
          textStyle: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: colors.inputFill,
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppRadii.input),
          borderSide: BorderSide(color: colors.border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppRadii.input),
          borderSide: BorderSide(color: colors.border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppRadii.input),
          borderSide: BorderSide(color: isDark ? AppColors.accentBlue : AppColors.primary, width: 1.5),
        ),
        labelStyle: TextStyle(color: colors.textMuted, fontSize: 13, fontWeight: FontWeight.w500),
        hintStyle: TextStyle(color: colors.textSubtle, fontSize: 14),
      ),
    );
  }

  static ThemeData get lightTheme => themeForLocale(const Locale('ar'), isDark: false);
  static ThemeData get darkTheme => themeForLocale(const Locale('ar'), isDark: true);
}

extension BuildContextThemeExtension on BuildContext {
  AppThemeColors get colors =>
      Theme.of(this).extension<AppThemeColors>() ??
      (Theme.of(this).brightness == Brightness.dark ? AppThemeColors.dark : AppThemeColors.light);
  bool get isDark => Theme.of(this).brightness == Brightness.dark;
}
