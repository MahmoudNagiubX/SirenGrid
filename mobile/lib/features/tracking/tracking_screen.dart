import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import '../../core/dev_preview.dart';
import '../../core/localization/locale_cubit.dart';
import '../../core/localization/siren_localizations.dart';
import '../../core/theme.dart';
import '../auth/auth_cubit.dart';
import '../emergency_home/emergency_service.dart';
import 'tracking_cubit.dart';

// ponytail: single authoritative TrackingScreen matching locked prototype tracking.html
class TrackingScreen extends StatefulWidget {
  final String? initialRequestId;
  final VoidCallback? onReturnHome;

  const TrackingScreen({
    super.key,
    this.initialRequestId,
    this.onReturnHome,
  });

  @override
  State<TrackingScreen> createState() => _TrackingScreenState();
}

class _TrackingScreenState extends State<TrackingScreen> {
  bool _previewShowActive = false;

  @override
  void initState() {
    super.initState();
    AuthCubit? authCubit;
    try {
      authCubit = context.read<AuthCubit>();
    } catch (_) {}
    if (authCubit?.state is! AuthPreview) {
      context.read<TrackingCubit>().startTracking(widget.initialRequestId);
    }
  }

  @override
  void didUpdateWidget(covariant TrackingScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    AuthCubit? authCubit;
    try {
      authCubit = context.read<AuthCubit>();
    } catch (_) {}
    if (authCubit?.state is! AuthPreview &&
        widget.initialRequestId != oldWidget.initialRequestId &&
        widget.initialRequestId != null) {
      context.read<TrackingCubit>().startTracking(widget.initialRequestId);
    }
  }

  @override
  Widget build(BuildContext context) {
    AuthCubit? authCubit;
    try {
      authCubit = context.watch<AuthCubit>();
    } catch (_) {
      try {
        authCubit = context.read<AuthCubit>();
      } catch (_) {}
    }
    final isPreview = authCubit?.state is AuthPreview;
    final isArabic = context.watch<LocaleCubit>().isArabic;
    final langCode = isArabic ? 'ar' : 'en';
    final colors = context.colors;

    return Scaffold(
      backgroundColor: colors.background,
      body: SafeArea(
        child: Column(
          children: [
            // Development-Only UI Preview Toggle
            if (isPreview)
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 24, 20, 16),
                child: Container(
                  key: const Key('tracking_preview_toggle_bar'),
                  padding: const EdgeInsets.all(4),
                  decoration: BoxDecoration(
                    color: context.isDark ? const Color(0xFF1E293B) : const Color(0xFFF1F5F9),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: colors.border),
                  ),
                  child: Row(
                    children: [
                      Expanded(
                        child: GestureDetector(
                          key: const Key('tracking_preview_empty_btn'),
                          onTap: () => setState(() => _previewShowActive = false),
                          child: Container(
                            padding: const EdgeInsets.symmetric(vertical: 8),
                            decoration: BoxDecoration(
                              color: !_previewShowActive
                                  ? (context.isDark ? const Color(0xFF334155) : Colors.white)
                                  : Colors.transparent,
                              borderRadius: BorderRadius.circular(8),
                              boxShadow: !_previewShowActive
                                  ? [const BoxShadow(color: Color(0x0F000000), blurRadius: 4, offset: Offset(0, 1))]
                                  : null,
                            ),
                            child: Text(
                              context.tr('tracking.preview_toggle_empty'),
                              textAlign: TextAlign.center,
                              style: TextStyle(
                                fontSize: 12,
                                fontWeight: !_previewShowActive ? FontWeight.w700 : FontWeight.w500,
                                color: !_previewShowActive ? colors.textPrimary : colors.textMuted,
                              ),
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(width: 4),
                      Expanded(
                        child: GestureDetector(
                          key: const Key('tracking_preview_active_btn'),
                          onTap: () => setState(() => _previewShowActive = true),
                          child: Container(
                            padding: const EdgeInsets.symmetric(vertical: 8),
                            decoration: BoxDecoration(
                              color: _previewShowActive
                                  ? (context.isDark ? const Color(0xFF334155) : Colors.white)
                                  : Colors.transparent,
                              borderRadius: BorderRadius.circular(8),
                              boxShadow: _previewShowActive
                                  ? [const BoxShadow(color: Color(0x0F000000), blurRadius: 4, offset: Offset(0, 1))]
                                  : null,
                            ),
                            child: Text(
                              context.tr('tracking.preview_toggle_active'),
                              textAlign: TextAlign.center,
                              style: TextStyle(
                                fontSize: 12,
                                fontWeight: _previewShowActive ? FontWeight.w700 : FontWeight.w500,
                                color: _previewShowActive ? colors.textPrimary : colors.textMuted,
                              ),
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),

            // Main Body Area
            Expanded(
              child: isPreview
                  ? (_previewShowActive
                      ? _buildActiveView(context, DevPreviewConfig.previewTrackingData, isArabic, langCode, isPreview: true)
                      : _buildEmptyView(context, isArabic))
                  : BlocBuilder<TrackingCubit, TrackingState>(
                      builder: (context, state) {
                        if (state is TrackingLoading) {
                          return const Center(
                            child: CircularProgressIndicator(color: AppColors.primaryNavy),
                          );
                        }

                        if (state is TrackingActive) {
                          return _buildActiveView(context, state.data, isArabic, langCode, isPreview: false);
                        }

                        if (state is TrackingError) {
                          return _buildErrorView(context, state.message, isArabic);
                        }

                        // Default: Canonical Empty State (VIEW A)
                        return _buildEmptyView(context, isArabic);
                      },
                    ),
            ),
          ],
        ),
      ),
    );
  }

  // VIEW A: Canonical Empty State (Default when no active emergency)
  Widget _buildEmptyView(BuildContext context, bool isArabic) {
    final colors = context.colors;
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            // Radar / Clock Icon Circle (64x64)
            Container(
              width: 64,
              height: 64,
              decoration: BoxDecoration(
                color: context.isDark ? const Color(0xFF1E293B) : AppColors.primarySubtle,
                shape: BoxShape.circle,
                boxShadow: const [
                  BoxShadow(
                    color: Color(0x0A000000),
                    blurRadius: 6,
                    offset: Offset(0, 2),
                  ),
                ],
              ),
              child: Icon(
                Icons.access_time_outlined,
                size: 32,
                color: context.isDark ? colors.textMuted : AppColors.textSecondary,
              ),
            ),
            const SizedBox(height: 24),

            // Headline
            Text(
              context.tr('tracking.empty_title'),
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 20,
                fontWeight: FontWeight.w700,
                color: colors.textPrimary,
                height: 1.3,
              ),
            ),
            const SizedBox(height: 12),

            // Subtext
            ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 300),
              child: Text(
                context.tr('tracking.empty_desc'),
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 14,
                  color: colors.textMuted,
                  height: 1.6,
                ),
              ),
            ),
            const SizedBox(height: 32),

            // Action Button: Return to Home
            SizedBox(
              width: 220,
              height: 48,
              child: ElevatedButton(
                key: const Key('tracking_return_home_btn'),
                onPressed: () {
                  if (widget.onReturnHome != null) {
                    widget.onReturnHome!();
                  } else if (Navigator.of(context).canPop()) {
                    Navigator.of(context).pop();
                  }
                },
                style: ElevatedButton.styleFrom(
                  backgroundColor: context.isDark ? AppColors.accentBlue : AppColors.primaryNavy,
                  foregroundColor: Colors.white,
                  elevation: 0,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(AppRadii.button),
                  ),
                ),
                child: Text(
                  context.tr('tracking.return_home'),
                  style: const TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  // VIEW B: Authoritative Active Tracking View
  Widget _buildActiveView(BuildContext context, TrackingData data, bool isArabic, String langCode, {bool isPreview = false}) {
    final colors = context.colors;
    final service = EmergencyService.fromBackendCode(data.service);
    final serviceTitle = isArabic
        ? 'طلب ${context.tr(service.titleKey)}'
        : '${context.tr(service.titleKey)} Request';

    // ETA display computation (never fabricated, strictly derived from backend eta_seconds)
    final String etaDisplay;
    if (data.etaSeconds != null) {
      final mins = (data.etaSeconds! / 60).round();
      if (mins <= 0) {
        etaDisplay = context.tr('tracking.eta_less_than_min');
      } else {
        etaDisplay = isArabic ? '~$mins دقيقة' : '~$mins min';
      }
    } else {
      etaDisplay = context.tr('tracking.eta_preparing');
    }

    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
      children: [
        // Request Provenance Pill (strictly SIMULATED or SYNTHETIC; never on REAL or unknown)
        if (data.hasRequestProvenance) ...[
          Builder(
            builder: (context) {
              final badgeText = _getRequestRealityBadgeText(context, data.dataReality, isArabic);
              if (badgeText == null) return const SizedBox.shrink();
              return Align(
                alignment: AlignmentDirectional.centerStart,
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: context.isDark ? const Color(0xFF78350F).withValues(alpha: 0.4) : const Color(0xFFFEF3C7),
                    borderRadius: BorderRadius.circular(AppRadii.pill),
                    border: Border.all(color: context.isDark ? const Color(0xFFB45309) : const Color(0xFFFCD34D)),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(
                        Icons.info_outline,
                        size: 14,
                        color: context.isDark ? const Color(0xFFFDE68A) : const Color(0xFF92400E),
                      ),
                      const SizedBox(width: 6),
                      Flexible(
                        child: Text(
                          badgeText,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w600,
                            color: context.isDark ? const Color(0xFFFDE68A) : const Color(0xFF92400E),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              );
            },
          ),
          const SizedBox(height: 16),
        ],

        // Request Status Card
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
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    context.tr('tracking.status_label'),
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: colors.textMuted,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Flexible(
                    child: Container(
                      key: const Key('track-status-badge'),
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                      decoration: BoxDecoration(
                        color: context.isDark ? const Color(0xFF1E3A8A) : AppColors.accentBlueLight,
                        borderRadius: BorderRadius.circular(AppRadii.pill),
                      ),
                      child: Text(
                        data.status.localizedBadge(langCode),
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w700,
                          color: context.isDark ? const Color(0xFF93C5FD) : AppColors.accentBlue,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              Text(
                serviceTitle,
                style: TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.w700,
                  color: colors.textPrimary,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                '${context.tr('tracking.ref_prefix')} ${data.requestId}',
                style: TextStyle(
                  fontSize: 12,
                  color: colors.textMuted,
                ),
              ),
              if (data.incidentId != null) ...[
                const SizedBox(height: 2),
                Text(
                  '${context.tr('tracking.incident_prefix')} ${data.incidentId}',
                  style: TextStyle(
                    fontSize: 12,
                    color: colors.textMuted,
                  ),
                ),
              ],
            ],
          ),
        ),
        const SizedBox(height: 16),

        // ETA Card
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: context.isDark ? const Color(0xFF1E293B) : AppColors.primaryNavy,
            borderRadius: BorderRadius.circular(AppRadii.card),
            border: context.isDark ? Border.all(color: colors.border) : null,
          ),
          child: Row(
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  color: context.isDark ? const Color(0x333B82F6) : const Color(0x1FFFFFFF),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(
                  Icons.timer_outlined,
                  color: context.isDark ? const Color(0xFF93C5FD) : Colors.white,
                  size: 22,
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      context.tr('tracking.eta_label'),
                      style: TextStyle(
                        fontSize: 11,
                        color: context.isDark ? colors.textMuted : const Color(0xCCFFFFFF),
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      etaDisplay,
                      style: const TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w700,
                        color: Colors.white,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),

        // Map View Box (Truthful non-map placeholder without fake routes)
        Container(
          height: 200,
          decoration: BoxDecoration(
            color: context.isDark ? const Color(0xFF1E293B) : const Color(0xFFE2E8F0),
            borderRadius: BorderRadius.circular(AppRadii.card),
            border: Border.all(color: colors.border),
          ),
          child: Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(
                  Icons.map_outlined,
                  size: 44,
                  color: context.isDark ? const Color(0xFF60A5FA) : AppColors.primaryNavy,
                ),
                const SizedBox(height: 8),
                Text(
                  context.tr('tracking.map_preview'),
                  style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w700,
                    color: context.isDark ? colors.textPrimary : AppColors.primaryNavy,
                  ),
                ),
                const SizedBox(height: 4),
                if (data.responder?.location != null) ...[
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    child: Text(
                      '${data.responder!.label ?? 'Unit'} • ${data.responder!.location!.lat.toStringAsFixed(4)}, ${data.responder!.location!.lon.toStringAsFixed(4)}',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        fontSize: 11,
                        color: colors.textMuted,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                  if (data.hasResponderProvenance)
                    Builder(
                      builder: (context) {
                        final responderBadge = _getResponderRealityBadgeText(
                          context,
                          data.responder?.dataReality,
                          isArabic,
                        );
                        if (responderBadge == null) return const SizedBox.shrink();
                        return Padding(
                          padding: const EdgeInsets.only(top: 4),
                          child: Container(
                            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                            decoration: BoxDecoration(
                              color: context.isDark ? const Color(0xFF78350F).withValues(alpha: 0.4) : const Color(0xFFFEF3C7),
                              borderRadius: BorderRadius.circular(AppRadii.pill),
                              border: Border.all(color: context.isDark ? const Color(0xFFB45309) : const Color(0xFFFCD34D)),
                            ),
                            child: Text(
                              responderBadge,
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
                ] else
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    child: Text(
                      context.tr('tracking.responder_unavailable'),
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        fontSize: 11,
                        color: colors.textMuted,
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 20),

        // Response Progress Timeline (Master Plan / Prototype Alignment)
        Text(
          context.tr('tracking.timeline_title'),
          style: TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w700,
            color: colors.textPrimary,
          ),
        ),
        const SizedBox(height: 12),
        _buildTimeline(context, data.status),
        const SizedBox(height: 24),

        // Action: View Empty State / Clear Request
        SizedBox(
          width: double.infinity,
          height: 44,
          child: OutlinedButton(
            key: const Key('tracking_view_empty_btn'),
            onPressed: () {
              if (isPreview) {
                setState(() => _previewShowActive = false);
              } else {
                context.read<TrackingCubit>().clearTracking();
              }
            },
            style: OutlinedButton.styleFrom(
              foregroundColor: colors.textMuted,
              side: BorderSide(color: colors.border),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(AppRadii.button),
              ),
            ),
            child: Text(
              context.tr('tracking.view_empty_btn'),
              style: TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w600,
                color: colors.textMuted,
              ),
            ),
          ),
        ),
      ],
    );
  }

  // Helper: Response Progress Timeline Steps
  Widget _buildTimeline(BuildContext context, CitizenRequestStatus status) {
    final isReceivedDone = true;
    final isReviewDone = status != CitizenRequestStatus.received;
    final isAssignedDone = status == CitizenRequestStatus.responseAssigned ||
        status == CitizenRequestStatus.enRoute ||
        status == CitizenRequestStatus.arrived ||
        status == CitizenRequestStatus.completed;
    final isEnRouteDone = status == CitizenRequestStatus.enRoute ||
        status == CitizenRequestStatus.arrived ||
        status == CitizenRequestStatus.completed;
    final isArrivedDone = status == CitizenRequestStatus.arrived ||
        status == CitizenRequestStatus.completed;

    return Column(
      children: [
        _buildTimelineRow(
          context,
          context.tr('tracking.timeline_received'),
          isDone: isReceivedDone,
          isActive: status == CitizenRequestStatus.received,
        ),
        _buildTimelineRow(
          context,
          context.tr('tracking.timeline_review'),
          isDone: isReviewDone,
          isActive: status == CitizenRequestStatus.underReview,
        ),
        _buildTimelineRow(
          context,
          context.tr('tracking.timeline_assigned'),
          isDone: isAssignedDone,
          isActive: status == CitizenRequestStatus.responseAssigned,
        ),
        _buildTimelineRow(
          context,
          context.tr('tracking.timeline_en_route'),
          isDone: isEnRouteDone,
          isActive: status == CitizenRequestStatus.enRoute,
        ),
        _buildTimelineRow(
          context,
          context.tr('tracking.timeline_arrived'),
          isDone: isArrivedDone,
          isActive: status == CitizenRequestStatus.arrived,
          isLast: true,
        ),
      ],
    );
  }

  Widget _buildTimelineRow(BuildContext context, String label, {bool isDone = false, bool isActive = false, bool isLast = false}) {
    final colors = context.colors;
    final Color iconColor;
    final IconData iconData;

    if (isDone && !isActive) {
      iconColor = const Color(0xFF10B981);
      iconData = Icons.check_circle;
    } else if (isActive) {
      iconColor = context.isDark ? const Color(0xFF60A5FA) : AppColors.accentBlue;
      iconData = Icons.radio_button_checked;
    } else {
      iconColor = colors.border;
      iconData = Icons.radio_button_unchecked;
    }

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Column(
          children: [
            Icon(iconData, color: iconColor, size: 20),
            if (!isLast)
              Container(
                width: 2,
                height: 24,
                color: isDone ? const Color(0xFF10B981) : colors.border,
              ),
          ],
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Padding(
            padding: const EdgeInsets.only(top: 2),
            child: Text(
              label,
              style: TextStyle(
                fontSize: 13,
                fontWeight: isActive ? FontWeight.w700 : FontWeight.w500,
                color: isDone || isActive ? colors.textPrimary : colors.textMuted,
              ),
            ),
          ),
        ),
      ],
    );
  }

  // Error view (retains active request ID for safe retry)
  Widget _buildErrorView(BuildContext context, String message, bool isArabic) {
    final colors = context.colors;
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.cloud_off_outlined, size: 56, color: colors.textMuted),
            const SizedBox(height: 16),
            Text(
              message,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 15,
                color: colors.textPrimary,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 20),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                ElevatedButton(
                  onPressed: () => context.read<TrackingCubit>().refreshActiveRequest(),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: context.isDark ? AppColors.accentBlue : AppColors.primaryNavy,
                    foregroundColor: Colors.white,
                  ),
                  child: Text(context.tr('tracking.retry_btn')),
                ),
                const SizedBox(width: 12),
                OutlinedButton(
                  onPressed: () => context.read<TrackingCubit>().clearTracking(),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: colors.textMuted,
                    side: BorderSide(color: colors.border),
                  ),
                  child: Text(context.tr('tracking.view_empty_btn')),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  String? _getRequestRealityBadgeText(BuildContext context, String? reality, bool isArabic) {
    if (reality == null) return null;
    final upper = reality.trim().toUpperCase();
    if (upper == 'SIMULATED') {
      return context.tr('tracking.badge_simulated');
    } else if (upper == 'SYNTHETIC') {
      return context.tr('tracking.badge_synthetic');
    }
    return null; // REAL or unknown -> no badge
  }

  String? _getResponderRealityBadgeText(BuildContext context, String? reality, bool isArabic) {
    if (reality == null) return null;
    final upper = reality.trim().toUpperCase();
    if (upper == 'SIMULATED') {
      return context.tr('tracking.responder_simulated');
    } else if (upper == 'SYNTHETIC') {
      return context.tr('tracking.responder_synthetic');
    }
    return null; // REAL or unknown -> no badge
  }
}

