import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import '../../../core/localization/siren_localizations.dart';
import '../../../core/theme.dart';
import '../../auth/auth_cubit.dart';
import '../emergency_service.dart';
import '../home_cubit.dart';

// ponytail: reusable native ConfirmationSheet driven by the selected EmergencyService & HomeCubit
class ConfirmationSheet extends StatefulWidget {
  final EmergencyService service;
  final ValueChanged<EmergencyService>? onConfirm;
  final ValueChanged<String>? onSubmitted;
  final VoidCallback? onCancel;

  const ConfirmationSheet({
    super.key,
    required this.service,
    this.onConfirm,
    this.onSubmitted,
    this.onCancel,
  });

  static Future<void> show({
    required BuildContext context,
    required EmergencyService service,
    ValueChanged<EmergencyService>? onConfirm,
    ValueChanged<String>? onSubmitted,
    VoidCallback? onCancel,
  }) {
    HomeCubit? homeCubit;
    AuthCubit? authCubit;
    try {
      homeCubit = context.read<HomeCubit>();
    } catch (_) {}
    try {
      authCubit = context.read<AuthCubit>();
    } catch (_) {}

    return showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => MultiBlocProvider(
        providers: [
          if (homeCubit != null) BlocProvider<HomeCubit>.value(value: homeCubit),
          if (authCubit != null) BlocProvider<AuthCubit>.value(value: authCubit),
        ],
        child: ConfirmationSheet(
          service: service,
          onConfirm: onConfirm,
          onSubmitted: onSubmitted,
          onCancel: onCancel,
        ),
      ),
    );
  }

  @override
  State<ConfirmationSheet> createState() => _ConfirmationSheetState();
}

class _ConfirmationSheetState extends State<ConfirmationSheet> {
  String? _previewNotice;

  EmergencyService get service => widget.service;
  ValueChanged<EmergencyService>? get onConfirm => widget.onConfirm;
  ValueChanged<String>? get onSubmitted => widget.onSubmitted;
  VoidCallback? get onCancel => widget.onCancel;

  @override
  Widget build(BuildContext context) {
    final isArabic = Directionality.of(context) == TextDirection.rtl;

    HomeCubit? homeCubit;
    AuthCubit? authCubit;
    try {
      homeCubit = context.read<HomeCubit>();
    } catch (_) {}
    try {
      authCubit = context.read<AuthCubit>();
    } catch (_) {}

    Widget buildSheetContent(BuildContext sheetContext, HomeState? state) {
      final isSubmitting = state is HomeSubmitting;
      final errorMessage = state is HomeError ? state.message : null;
      final colors = sheetContext.colors;

      return Container(
        decoration: BoxDecoration(
          color: colors.surface,
          borderRadius: const BorderRadius.vertical(top: Radius.circular(AppRadii.sheet)),
        ),
        padding: const EdgeInsets.fromLTRB(24, 12, 24, 24),
        child: SafeArea(
          top: false,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // Drag Handle
              Center(
                child: Container(
                  width: 36,
                  height: 4,
                  margin: const EdgeInsets.only(bottom: 20),
                  decoration: BoxDecoration(
                    color: colors.border,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),

              // Selected Service Header (Reusing authoritative metadata)
              Row(
                children: [
                  Container(
                    width: 48,
                    height: 48,
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.topLeft,
                        end: Alignment.bottomRight,
                        colors: [service.fromColor, service.toColor],
                      ),
                      borderRadius: BorderRadius.circular(14),
                      boxShadow: [
                        BoxShadow(
                          color: service.toColor.withValues(alpha: 0.2),
                          blurRadius: 8,
                          offset: const Offset(0, 3),
                        ),
                      ],
                    ),
                    child: Center(
                      child: service.buildIcon(
                        color: Colors.white,
                        size: 24,
                      ),
                    ),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          context.tr(service.titleKey),
                          style: TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w700,
                            color: colors.textPrimary,
                          ),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          context.tr(service.subtitleKey),
                          style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w400,
                            color: colors.textMuted,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),

              // Location Readiness Card (Truthful: states current GPS acquisition upon confirm)
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                decoration: BoxDecoration(
                  color: colors.neutralCard,
                  borderRadius: BorderRadius.circular(AppRadii.input),
                  border: Border.all(color: colors.border),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Padding(
                      padding: const EdgeInsets.only(top: 2),
                      child: Icon(
                        Icons.location_on_outlined,
                        size: 18,
                        color: colors.textMuted,
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            context.tr('confirm.location_title'),
                            style: TextStyle(
                              fontSize: 12,
                              fontWeight: FontWeight.w700,
                              color: colors.textPrimary,
                            ),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            isSubmitting
                                ? (isArabic ? 'جاري تحديد إحداثيات الـ GPS الحالية...' : 'Acquiring current device GPS coordinates...')
                                : (isArabic ? 'سيتم تحديد إحداثيات موقعك الحالية بدقة فور التأكيد' : 'Current device GPS coordinates acquired upon confirmation'),
                            style: TextStyle(
                              fontSize: 11,
                              color: colors.textMuted,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),

              // Error Banner (when submission fails)
              if (errorMessage != null) ...[
                Container(
                  key: const Key('confirm_sheet_error_banner'),
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                  decoration: BoxDecoration(
                    color: const Color(0xFFFEF2F2),
                    borderRadius: BorderRadius.circular(AppRadii.input),
                    border: Border.all(color: const Color(0xFFF87171)),
                  ),
                  child: Row(
                    children: [
                      const Icon(Icons.error_outline, size: 18, color: Color(0xFFDC2626)),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          errorMessage,
                          style: const TextStyle(fontSize: 12, color: Color(0xFF991B1B)),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 12),
              ],

              // Explanatory Text
              Text(
                context.tr('confirm.explanation'),
                style: const TextStyle(
                  fontSize: 12,
                  height: 1.6,
                  color: AppColors.textMuted,
                ),
              ),
              const SizedBox(height: 20),
              // Preview Mode Submission Disabled Banner
              if (_previewNotice != null) ...[
                Container(
                  key: const Key('confirm_preview_banner'),
                  margin: const EdgeInsets.only(bottom: 12),
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                  decoration: BoxDecoration(
                    color: const Color(0xFFFEF3C7),
                    borderRadius: BorderRadius.circular(AppRadii.input),
                    border: Border.all(color: const Color(0xFFFCD34D)),
                  ),
                  child: Row(
                    children: [
                      const Icon(Icons.info_outline, size: 18, color: Color(0xFF92400E)),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          _previewNotice!,
                          style: const TextStyle(
                            fontSize: 12,
                            color: Color(0xFF92400E),
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],

              // Confirm Button (disables during submission to prevent duplicate taps)
              ElevatedButton(
                key: const Key('confirm_sheet_submit_button'),
                onPressed: isSubmitting
                    ? null
                    : () {
                        // CRITICAL PREVIEW SAFETY CONSTRAINT: Block emergency submission in UI Preview Mode
                        if (authCubit?.state is AuthPreview) {
                          final notice = context.tr('confirm.preview_blocked');
                          setState(() {
                            _previewNotice = notice;
                          });
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              key: const Key('confirm_preview_snack_bar'),
                              content: Text(notice),
                              backgroundColor: AppColors.primaryNavy,
                              behavior: SnackBarBehavior.floating,
                              duration: const Duration(seconds: 3),
                            ),
                          );
                          return;
                        }

                        if (onSubmitted != null && homeCubit != null) {
                          if (state is HomeError) {
                            homeCubit.retryLastSubmission();
                          } else {
                            String? citizenRef;
                            final authState = authCubit?.state;
                            if (authState is Authenticated) {
                              citizenRef = authState.profile.citizenReference;
                            }
                            homeCubit.submitEmergency(
                              service: service,
                              citizenReference: citizenRef,
                            );
                          }
                        } else {
                          // Standalone widget test callback fallback
                          Navigator.of(context).pop();
                          onConfirm?.call(service);
                        }
                      },
                style: ElevatedButton.styleFrom(
                  minimumSize: const Size.fromHeight(AppDimensions.buttonHeight),
                  backgroundColor: service.confirmButtonColor,
                  foregroundColor: Colors.white,
                  disabledBackgroundColor: service.confirmButtonColor.withValues(alpha: 0.6),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(AppRadii.button),
                  ),
                ),
                child: isSubmitting
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.white,
                        ),
                      )
                    : Text(
                        state is HomeError
                            ? (isArabic ? 'إعادة المحاولة' : 'Retry Emergency Request')
                            : context.tr(service.confirmBtnKey),
                        style: const TextStyle(
                          fontSize: 15,
                          fontWeight: FontWeight.w600,
                          color: Colors.white,
                        ),
                      ),
              ),
              const SizedBox(height: 10),

              // Cancel Button (disabled during submission)
              OutlinedButton(
                key: const Key('confirm_sheet_cancel_button'),
                onPressed: isSubmitting
                    ? null
                    : () {
                        Navigator.of(context).pop();
                        onCancel?.call();
                      },
                style: OutlinedButton.styleFrom(
                  minimumSize: const Size.fromHeight(AppDimensions.buttonHeight),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(AppRadii.button),
                  ),
                ),
                child: Text(
                  context.tr('confirm.cancel'),
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                    color: colors.textPrimary,
                  ),
                ),
              ),
            ],
          ),
        ),
      );
    }

    if (homeCubit != null) {
      return BlocConsumer<HomeCubit, HomeState>(
        bloc: homeCubit,
        listener: (sheetContext, state) {
          if (state is HomeSubmitted) {
            Navigator.of(sheetContext).pop();
            onSubmitted?.call(state.requestId);
          }
        },
        builder: (sheetContext, state) => buildSheetContent(sheetContext, state),
      );
    }

    return buildSheetContent(context, null);
  }
}

