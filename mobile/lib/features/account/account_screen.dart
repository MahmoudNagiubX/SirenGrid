import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import '../../core/localization/locale_cubit.dart';
import '../../core/localization/siren_localizations.dart';
import '../../core/theme.dart';
import '../auth/auth_cubit.dart';
import '../settings/settings_screen.dart';

// ponytail: single authoritative AccountScreen matching locked prototype account.html
class AccountScreen extends StatelessWidget {
  const AccountScreen({super.key});

  String _getInitials(String displayName, bool isArabic) {
    final clean = displayName.trim();
    if (clean.isEmpty) return isArabic ? 'م' : 'C';
    final parts = clean.split(RegExp(r'\s+'));
    if (parts.length >= 2) {
      final first = parts[0].isNotEmpty ? parts[0][0] : '';
      final second = parts[1].isNotEmpty ? parts[1][0] : '';
      return '$first.$second';
    }
    return clean.isNotEmpty ? clean[0] : (isArabic ? 'م' : 'C');
  }

  @override
  Widget build(BuildContext context) {
    final authState = context.watch<AuthCubit>().state;
    final profile = authState.profile;
    final isArabic = context.watch<LocaleCubit>().isArabic;
    final colors = context.colors;

    final displayName = profile?.displayName.isNotEmpty == true
        ? profile!.displayName
        : (isArabic ? 'مواطن' : 'Citizen');
    final initials = _getInitials(displayName, isArabic);

    return Scaffold(
      backgroundColor: colors.background,
      body: SafeArea(
        child: Column(
          children: [
            // Top Header: Title & Settings Shortcut
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    context.tr('account.title'),
                    style: TextStyle(
                      fontSize: 22,
                      fontWeight: FontWeight.w700,
                      color: colors.textPrimary,
                    ),
                  ),
                  IconButton(
                    key: const Key('account_settings_shortcut'),
                    icon: Icon(Icons.settings_outlined, color: colors.textMuted),
                    tooltip: context.tr('settings.title'),
                    onPressed: () {
                      Navigator.of(context).push(
                        MaterialPageRoute(builder: (_) => const SettingsScreen()),
                      );
                    },
                  ),
                ],
              ),
            ),

            // Main Account Content
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
                children: [
                  // User Profile Card
                  Container(
                    padding: const EdgeInsets.all(24),
                    decoration: BoxDecoration(
                      color: colors.surface,
                      borderRadius: BorderRadius.circular(AppRadii.card),
                      border: Border.all(color: colors.border),
                    ),
                    child: Column(
                      children: [
                        // Large Avatar Circle
                        Container(
                          width: 76,
                          height: 76,
                          decoration: const BoxDecoration(
                            color: AppColors.primaryNavy,
                            shape: BoxShape.circle,
                          ),
                          alignment: Alignment.center,
                          child: Text(
                            initials,
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 22,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ),
                        const SizedBox(height: 12),

                        // Full Name from authoritative CitizenProfile
                        Text(
                          displayName,
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w700,
                            color: colors.textPrimary,
                            height: 1.3,
                          ),
                        ),
                        const SizedBox(height: 6),

                        // Identity Verification Badge (authoritative mapping)
                        _buildIdentityStatusBadge(context, profile?.status, isArabic),
                        const SizedBox(height: 8),

                        // Data Reality Provenance Pill (strictly SIMULATED or SYNTHETIC; never on REAL or unknown)
                        Builder(
                          builder: (context) {
                            final badgeText = _getRealityBadgeText(context, profile?.dataReality, isArabic);
                            if (badgeText == null) return const SizedBox.shrink();
                            return Padding(
                              padding: const EdgeInsets.only(bottom: 8),
                              child: Container(
                                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
                                decoration: BoxDecoration(
                                  color: context.isDark ? const Color(0xFF78350F).withValues(alpha: 0.4) : const Color(0xFFFEF3C7),
                                  borderRadius: BorderRadius.circular(AppRadii.pill),
                                  border: Border.all(color: context.isDark ? const Color(0xFFB45309) : const Color(0xFFFCD34D)),
                                ),
                                child: Text(
                                  badgeText,
                                  style: TextStyle(
                                    fontSize: 10,
                                    fontWeight: FontWeight.w600,
                                    color: context.isDark ? const Color(0xFFFDE68A) : const Color(0xFF92400E),
                                  ),
                                ),
                              ),
                            );
                          },
                        ),

                        // Phone Number (Always LTR presentation)
                        Directionality(
                          textDirection: TextDirection.ltr,
                          child: Text(
                            profile?.phone ?? '',
                            style: TextStyle(
                              fontSize: 14,
                              color: colors.textMuted,
                              fontWeight: FontWeight.w500,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),

                  // Key-Value Identification Records Card
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: colors.surface,
                      borderRadius: BorderRadius.circular(AppRadii.card),
                      border: Border.all(color: colors.border),
                    ),
                    child: Column(
                      children: [
                        // National ID (Masked)
                        _buildKeyValueRow(
                          context: context,
                          label: context.tr('account.nid_label'),
                          valueWidget: Directionality(
                            textDirection: TextDirection.ltr,
                            child: Text(
                              profile?.maskedNationalId ?? '•••• •••• •••• ----',
                              style: TextStyle(
                                fontSize: 13,
                                fontWeight: FontWeight.w600,
                                color: colors.textPrimary,
                                letterSpacing: 1.0,
                              ),
                            ),
                          ),
                        ),
                        Divider(color: colors.border, height: 24),

                        // Citizen Reference
                        _buildKeyValueRow(
                          context: context,
                          label: context.tr('account.citizen_ref_label'),
                          valueWidget: Directionality(
                            textDirection: TextDirection.ltr,
                            child: Text(
                              profile?.citizenReference ?? '----',
                              style: TextStyle(
                                fontSize: 13,
                                fontWeight: FontWeight.w600,
                                color: colors.textPrimary,
                              ),
                            ),
                          ),
                        ),
                        Divider(color: colors.border, height: 24),

                        // Registered Address (Truthful unavailable state per Correction 2)
                        _buildKeyValueRow(
                          context: context,
                          label: context.tr('account.address_label'),
                          valueWidget: Text(
                            context.tr('account.address_unavailable'),
                            style: TextStyle(
                              fontSize: 13,
                              fontWeight: FontWeight.w600,
                              color: colors.textMuted,
                            ),
                          ),
                        ),
                        Divider(color: colors.border, height: 24),

                        // Notification Permission (Truthful unverified state per Requirement 7)
                        _buildKeyValueRow(
                          context: context,
                          label: context.tr('account.notifications_label'),
                          valueWidget: Text(
                            context.tr('account.notifications_not_checked'),
                            style: TextStyle(
                              fontSize: 12,
                              fontWeight: FontWeight.w600,
                              color: colors.textMuted,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),

                  // Quick Link to Settings
                  InkWell(
                    key: const Key('account_settings_link_btn'),
                    onTap: () {
                      Navigator.of(context).push(
                        MaterialPageRoute(builder: (_) => const SettingsScreen()),
                      );
                    },
                    borderRadius: BorderRadius.circular(AppRadii.button),
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                      decoration: BoxDecoration(
                        color: colors.surface,
                        borderRadius: BorderRadius.circular(AppRadii.button),
                        border: Border.all(color: colors.border),
                      ),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text(
                            context.tr('settings.title'),
                            style: TextStyle(
                              fontSize: 14,
                              fontWeight: FontWeight.w600,
                              color: colors.textPrimary,
                            ),
                          ),
                          Icon(
                            isArabic ? Icons.chevron_left_rounded : Icons.chevron_right_rounded,
                            color: colors.textMuted,
                            size: 20,
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 24),

                  // Sign Out Action
                  SizedBox(
                    width: double.infinity,
                    height: 48,
                    child: OutlinedButton.icon(
                      key: const Key('account_sign_out_btn'),
                      onPressed: () => context.read<AuthCubit>().logout(),
                      icon: const Icon(Icons.logout_rounded, size: 18),
                      label: Text(
                        context.tr('account.sign_out'),
                        style: const TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: AppColors.emergencyRed,
                        side: const BorderSide(color: AppColors.emergencyRed),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(AppRadii.button),
                        ),
                      ),
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

  String? _getRealityBadgeText(BuildContext context, String? dataReality, bool isArabic) {
    if (dataReality == null) return null;
    final val = dataReality.trim().toUpperCase();
    if (val == 'SIMULATED') {
      return context.tr('account.badge_simulated');
    } else if (val == 'SYNTHETIC') {
      return context.tr('account.badge_synthetic');
    }
    return null; // REAL, unknown, or empty -> do not guess, no badge
  }

  Widget _buildIdentityStatusBadge(BuildContext context, String? status, bool isArabic) {
    final raw = status?.trim() ?? '';
    final bool isVerified = raw.toUpperCase() == 'VERIFIED' || raw.toUpperCase() == 'DEMO_VERIFIED';

    if (isVerified) {
      return Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
        decoration: BoxDecoration(
          color: context.isDark ? const Color(0xFF064E3B) : const Color(0xFFECFDF5),
          borderRadius: BorderRadius.circular(AppRadii.pill),
          border: Border.all(color: context.isDark ? const Color(0xFF059669) : const Color(0xFFA7F3D0)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.check_circle_outline_rounded,
              size: 12,
              color: context.isDark ? const Color(0xFF6EE7B7) : const Color(0xFF047857),
            ),
            const SizedBox(width: 4),
            Text(
              isArabic ? 'تم التحقق' : 'Verified',
              style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w600,
                color: context.isDark ? const Color(0xFF6EE7B7) : const Color(0xFF047857),
              ),
            ),
          ],
        ),
      );
    }

    // Do not invent a 'Pending' state unless backend contract explicitly defines it.
    // Render other authoritative values safely without inventing their meaning.
    if (raw.isEmpty) {
      return const SizedBox.shrink();
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: context.isDark ? const Color(0xFF334155) : const Color(0xFFF1F5F9),
        borderRadius: BorderRadius.circular(AppRadii.pill),
        border: Border.all(color: context.isDark ? const Color(0xFF475569) : const Color(0xFFCBD5E1)),
      ),
      child: Text(
        raw,
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w600,
          color: context.isDark ? const Color(0xFFCBD5E1) : const Color(0xFF475569),
        ),
      ),
    );
  }

  Widget _buildKeyValueRow({required BuildContext context, required String label, required Widget valueWidget}) {
    final colors = context.colors;
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(
          label,
          style: TextStyle(
            fontSize: 13,
            color: colors.textMuted,
          ),
        ),
        Flexible(child: valueWidget),
      ],
    );
  }
}
