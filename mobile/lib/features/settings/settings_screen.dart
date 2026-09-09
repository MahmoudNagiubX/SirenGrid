import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import '../../core/config.dart';
import '../../core/localization/locale_cubit.dart';
import '../../core/localization/siren_localizations.dart';
import '../../core/theme.dart';
import '../../core/theme_cubit.dart';

// ponytail: single authoritative SettingsScreen matching locked prototype settings.html
class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final isArabic = context.watch<LocaleCubit>().isArabic;
    final currentLanguageOption = context.watch<LocaleCubit>().currentOption;
    final currentThemeMode = context.watch<ThemeCubit>().state;
    final colors = context.colors;

    return Scaffold(
      backgroundColor: colors.background,
      body: SafeArea(
        child: Column(
          children: [
            // Top Header with Back Navigation to Account
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
              child: Row(
                children: [
                  IconButton(
                    key: const Key('settings_back_button'),
                    onPressed: () => Navigator.of(context).pop(),
                    icon: Icon(
                      isArabic ? Icons.arrow_forward_rounded : Icons.arrow_back_rounded,
                      color: colors.textPrimary,
                    ),
                    tooltip: isArabic ? 'رجوع' : 'Back',
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          context.tr('settings.title'),
                          style: TextStyle(
                            fontSize: 22,
                            fontWeight: FontWeight.w700,
                            color: colors.textPrimary,
                            height: 1.2,
                          ),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          context.tr('settings.subtitle'),
                          style: TextStyle(
                            fontSize: 12,
                            color: colors.textMuted,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),

            // Main Settings Content
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
                children: [
                  // Card 1: Preferences (تفضيلات التطبيق)
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: colors.surface,
                      borderRadius: BorderRadius.circular(AppRadii.card),
                      border: Border.all(color: colors.border),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Text(
                          context.tr('settings.preferences_section'),
                          style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w700,
                            color: colors.textMuted,
                            letterSpacing: 0.5,
                          ),
                        ),
                        const SizedBox(height: 12),

                        // Language Preference Row
                        Row(
                          children: [
                            Container(
                              width: 40,
                              height: 40,
                              decoration: BoxDecoration(
                                color: colors.accentBlueLight,
                                borderRadius: BorderRadius.circular(12),
                              ),
                              child: const Icon(
                                Icons.language_rounded,
                                color: AppColors.accentBlue,
                                size: 20,
                              ),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    context.tr('settings.language_label'),
                                    style: TextStyle(
                                      fontSize: 14,
                                      fontWeight: FontWeight.w600,
                                      color: colors.textPrimary,
                                    ),
                                  ),
                                  const SizedBox(height: 2),
                                  Text(
                                    context.tr('settings.language_desc'),
                                    style: TextStyle(
                                      fontSize: 11,
                                      color: colors.textMuted,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            const SizedBox(width: 8),
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                              decoration: BoxDecoration(
                                color: colors.accentBlueLight,
                                borderRadius: BorderRadius.circular(8),
                              ),
                              child: DropdownButtonHideUnderline(
                                child: DropdownButton<AppLanguageOption>(
                                  key: const Key('settings_language_dropdown'),
                                  value: currentLanguageOption,
                                  isDense: true,
                                  borderRadius: BorderRadius.circular(12),
                                  dropdownColor: colors.surfaceElevated,
                                  style: TextStyle(
                                    fontSize: 12,
                                    fontWeight: FontWeight.w600,
                                    color: AppColors.accentBlue,
                                    fontFamily: isArabic ? 'Rubik' : 'Lexend',
                                  ),
                                  icon: const Icon(
                                    Icons.unfold_more_rounded,
                                    size: 14,
                                    color: AppColors.accentBlue,
                                  ),
                                  items: [
                                    DropdownMenuItem(
                                      value: AppLanguageOption.system,
                                      child: Text(isArabic ? 'لغة الجهاز' : 'Device Default'),
                                    ),
                                    const DropdownMenuItem(
                                      value: AppLanguageOption.en,
                                      child: Text('English'),
                                    ),
                                    const DropdownMenuItem(
                                      value: AppLanguageOption.ar,
                                      child: Text('العربية'),
                                    ),
                                  ],
                                  onChanged: (option) {
                                    if (option != null) {
                                      context.read<LocaleCubit>().setLanguageOption(option);
                                    }
                                  },
                                ),
                              ),
                            ),
                          ],
                        ),
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 12),
                          child: Divider(color: colors.border, height: 1),
                        ),

                        // Appearance / Theme Preference Row
                        Row(
                          children: [
                            Container(
                              width: 40,
                              height: 40,
                              decoration: BoxDecoration(
                                color: context.isDark ? const Color(0x332563EB) : const Color(0xFFFEF3C7),
                                borderRadius: BorderRadius.circular(12),
                              ),
                              child: Icon(
                                context.isDark ? Icons.dark_mode_outlined : Icons.light_mode_outlined,
                                color: context.isDark ? AppColors.accentBlue : const Color(0xFFD97706),
                                size: 20,
                              ),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    context.tr('settings.theme_label'),
                                    style: TextStyle(
                                      fontSize: 14,
                                      fontWeight: FontWeight.w600,
                                      color: colors.textPrimary,
                                    ),
                                  ),
                                  const SizedBox(height: 2),
                                  Text(
                                    context.tr('settings.theme_desc'),
                                    style: TextStyle(
                                      fontSize: 11,
                                      color: colors.textMuted,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            const SizedBox(width: 8),
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                              decoration: BoxDecoration(
                                color: colors.neutralCard,
                                borderRadius: BorderRadius.circular(8),
                              ),
                              child: DropdownButtonHideUnderline(
                                child: DropdownButton<ThemeMode>(
                                  key: const Key('settings_theme_dropdown'),
                                  value: currentThemeMode,
                                  isDense: true,
                                  borderRadius: BorderRadius.circular(12),
                                  dropdownColor: colors.surfaceElevated,
                                  style: TextStyle(
                                    fontSize: 12,
                                    fontWeight: FontWeight.w600,
                                    color: colors.textPrimary,
                                    fontFamily: isArabic ? 'Rubik' : 'Lexend',
                                  ),
                                  icon: Icon(
                                    Icons.unfold_more_rounded,
                                    size: 14,
                                    color: colors.textMuted,
                                  ),
                                  items: [
                                    DropdownMenuItem(
                                      value: ThemeMode.light,
                                      child: Text(isArabic ? 'فاتح' : 'Light'),
                                    ),
                                    DropdownMenuItem(
                                      value: ThemeMode.dark,
                                      child: Text(isArabic ? 'داكن' : 'Dark'),
                                    ),
                                  ],
                                  onChanged: (mode) {
                                    if (mode != null) {
                                      context.read<ThemeCubit>().setThemeMode(mode);
                                    }
                                  },
                                ),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),

                  // Card 2: Support & System (الدعم والنظام)
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: colors.surface,
                      borderRadius: BorderRadius.circular(AppRadii.card),
                      border: Border.all(color: colors.border),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Text(
                          context.tr('settings.support_section'),
                          style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w700,
                            color: colors.textMuted,
                            letterSpacing: 0.5,
                          ),
                        ),
                        const SizedBox(height: 12),

                        // Emergency Hotlines Label
                        Text(
                          context.tr('settings.hotlines_label'),
                          style: TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                            color: colors.textPrimary,
                          ),
                        ),
                        const SizedBox(height: 10),

                        // Hotlines Row (Police 122, Ambulance 123, Fire 180 from AppConfig)
                        Row(
                          children: [
                            Expanded(
                              child: _buildHotlineCard(
                                context: context,
                                label: context.tr('settings.police'),
                                number: AppConfig.hotlinePolice,
                              ),
                            ),
                            const SizedBox(width: 8),
                            Expanded(
                              child: _buildHotlineCard(
                                context: context,
                                label: context.tr('settings.ambulance'),
                                number: AppConfig.hotlineAmbulance,
                              ),
                            ),
                            const SizedBox(width: 8),
                            Expanded(
                              child: _buildHotlineCard(
                                context: context,
                                label: context.tr('settings.fire'),
                                number: AppConfig.hotlineFire,
                              ),
                            ),
                          ],
                        ),
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 14),
                          child: Divider(color: colors.border, height: 1),
                        ),

                        // App Version (CANONICAL CONTENT CONFLICT preserved: Cairo Operations vs Nasr City Core)
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text(
                              context.tr('settings.version_label'),
                              style: TextStyle(
                                fontSize: 13,
                                fontWeight: FontWeight.w600,
                                color: colors.textPrimary,
                              ),
                            ),
                            Flexible(
                              child: Text(
                                context.tr('settings.version_val'),
                                textAlign: TextAlign.end,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  fontSize: 11,
                                  color: colors.textMuted,
                                  fontWeight: FontWeight.w500,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildHotlineCard({
    required BuildContext context,
    required String label,
    required String number,
  }) {
    final colors = context.colors;
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 8),
      decoration: BoxDecoration(
        color: colors.neutralCard,
        borderRadius: BorderRadius.circular(AppRadii.button),
        border: Border.all(color: colors.border),
      ),
      child: Column(
        children: [
          Text(
            label,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: 11,
              color: colors.textMuted,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            number,
            style: TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.w700,
              color: colors.textPrimary,
            ),
          ),
        ],
      ),
    );
  }
}
