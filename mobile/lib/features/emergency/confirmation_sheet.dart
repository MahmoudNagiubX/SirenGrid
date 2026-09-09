import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import '../../design/components/sg_buttons.dart';
import '../../design/components/sg_feedback.dart';
import '../../design/components/sg_nav.dart';
import '../../design/tokens.dart';
import '../../l10n/strings.dart';
import 'emergency_service.dart';
import 'home_cubit.dart';

/// Request Confirmation (brief §3 / §15) — a bottom sheet over Home, not a
/// navigation screen. `Confirm` acquires a fresh GPS fix and submits exactly
/// once (the [HomeCubit] enforces the single-submit + idempotency lifecycle).
///
/// Returns the created request id on authoritative success, or null on
/// cancel / dismissal.
Future<HomeSubmitted?> showConfirmationSheet(
  BuildContext context, {
  required EmergencyService service,
}) {
  final cubit = context.read<HomeCubit>();
  cubit.reset();
  return showModalBottomSheet<HomeSubmitted?>(
    context: context,
    isScrollControlled: true,
    isDismissible: true,
    enableDrag: true,
    barrierColor: const Color(0x702B2D42),
    backgroundColor: Colors.transparent,
    builder: (sheetContext) => BlocProvider.value(
      value: cubit,
      child: _ConfirmationBody(service: service),
    ),
  );
}

class _ConfirmationBody extends StatelessWidget {
  const _ConfirmationBody({required this.service});
  final EmergencyService service;

  @override
  Widget build(BuildContext context) {
    return BlocConsumer<HomeCubit, HomeState>(
      listenWhen: (_, s) => s is HomeSubmitted || s is HomeSubmitFailure,
      listener: (context, state) {
        if (state is HomeSubmitted) {
          Navigator.of(context).pop(state);
        }
      },
      builder: (context, state) {
        final submitting = state is HomeSubmitting;
        final failure = state is HomeSubmitFailure ? state : null;
        final label = context.tr(service.labelKey).toLowerCase();

        return SgBottomSheet(
          child: submitting
              ? SgLoadingState(
                  label: context
                      .tr('confirm.sending')
                      .replaceFirst('request', '$label request'),
                )
              : Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '${context.tr('confirm.title')} $label?',
                      style: SgType.cardHeading.copyWith(
                        color: SgColors.textPrimary,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      context.tr('confirm.body'),
                      style: SgType.caption.copyWith(color: SgColors.textMuted),
                    ),
                    if (failure != null) ...[
                      const SizedBox(height: 14),
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 12,
                          vertical: 10,
                        ),
                        decoration: BoxDecoration(
                          color: SgColors.emergencySoft,
                          borderRadius: BorderRadius.circular(SgRadius.control),
                          border: Border.all(color: SgColors.emergencyBorder),
                        ),
                        child: Text(
                          _resolve(context, failure.message),
                          style: SgType.caption.copyWith(
                            color: SgColors.emergencyHover,
                          ),
                        ),
                      ),
                    ],
                    const SizedBox(height: 20),
                    Row(
                      children: [
                        Expanded(
                          child: SgSecondaryButton(
                            label: context.tr('confirm.cancel'),
                            full: true,
                            onPressed: () => Navigator.of(context).pop(),
                          ),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: SgEmergencyButton(
                            label: failure != null && failure.canRetry
                                ? context.tr('common.retry')
                                : context.tr('confirm.submit'),
                            full: true,
                            onPressed: () {
                              final cubit = context.read<HomeCubit>();
                              if (failure != null && failure.canRetry) {
                                cubit.retry();
                              } else {
                                cubit.submit(service);
                              }
                            },
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
        );
      },
    );
  }

  static String _resolve(BuildContext context, String key) =>
      key.contains('.') && !key.contains(' ') ? context.tr(key) : key;
}
