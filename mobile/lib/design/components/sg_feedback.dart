import 'package:flutter/material.dart';

import '../sg_icon.dart';
import '../tokens.dart';

enum SgChipTone { neutral, info, active, urgent, urgentSoft }

/// Small pill status indicator — "EN ROUTE" atop Tracking, neutral tags
/// elsewhere. `urgent` is a solid red fill so an active emergency reads at a
/// glance. Severity and calm status stay visually distinct.
class SgStatusChip extends StatefulWidget {
  const SgStatusChip(
    this.label, {
    super.key,
    this.tone = SgChipTone.neutral,
    this.dot = true,
    this.pulsing = false,
  });

  final String label;
  final SgChipTone tone;
  final bool dot;
  final bool pulsing;

  @override
  State<SgStatusChip> createState() => _SgStatusChipState();
}

class _SgStatusChipState extends State<SgStatusChip>
    with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 2000),
  );

  @override
  void initState() {
    super.initState();
    if (widget.pulsing) _c.repeat();
  }

  @override
  void didUpdateWidget(covariant SgStatusChip old) {
    super.didUpdateWidget(old);
    if (widget.pulsing && !_c.isAnimating) _c.repeat();
    if (!widget.pulsing && _c.isAnimating) _c.stop();
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  ({Color? bg, Gradient? grad, Color fg, Color dot}) get _style =>
      switch (widget.tone) {
        SgChipTone.neutral => (
          bg: SgColors.bgSunken,
          grad: null,
          fg: SgColors.textSecondary,
          dot: SgColors.gray500,
        ),
        SgChipTone.info => (
          bg: SgColors.infoSoft,
          grad: null,
          fg: SgColors.infoStrong,
          dot: SgColors.infoStrong,
        ),
        SgChipTone.active => (
          bg: SgColors.navy900,
          grad: null,
          fg: Colors.white,
          dot: Colors.white,
        ),
        SgChipTone.urgent => (
          bg: null,
          grad: SgColors.gradientEmergency,
          fg: Colors.white,
          dot: Colors.white,
        ),
        SgChipTone.urgentSoft => (
          bg: SgColors.emergencySoft,
          grad: null,
          fg: SgColors.emergencyHover,
          dot: SgColors.emergency,
        ),
      };

  @override
  Widget build(BuildContext context) {
    final s = _style;
    final reduceMotion = MediaQuery.maybeDisableAnimationsOf(context) ?? false;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 6),
      decoration: BoxDecoration(
        color: s.bg,
        gradient: s.grad,
        borderRadius: BorderRadius.circular(SgRadius.pill),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (widget.dot) ...[
            SizedBox(
              width: 7,
              height: 7,
              child: Stack(
                clipBehavior: Clip.none,
                alignment: Alignment.center,
                children: [
                  if (widget.pulsing && !reduceMotion)
                    AnimatedBuilder(
                      animation: _c,
                      builder: (context, _) => Opacity(
                        opacity: (1 - _c.value) * 0.9,
                        child: Transform.scale(
                          scale: 0.7 + _c.value * 1.3,
                          child: Container(
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              border: Border.all(color: s.dot, width: 1.5),
                            ),
                          ),
                        ),
                      ),
                    ),
                  Container(
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: s.dot,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 7),
          ],
          Text(
            widget.label.toUpperCase(),
            style: SgType.chip.copyWith(color: s.fg),
          ),
        ],
      ),
    );
  }
}

enum SgAlertTone { urgent, navy }

/// Full-width prominent inline banner (Clear-the-Way + similar non-blocking).
class SgAlertBanner extends StatelessWidget {
  const SgAlertBanner({
    super.key,
    required this.message,
    this.icon = 'siren',
    this.tone = SgAlertTone.urgent,
    this.onDismiss,
  });

  final String message;
  final String icon;
  final SgAlertTone tone;
  final VoidCallback? onDismiss;

  @override
  Widget build(BuildContext context) {
    final bg = tone == SgAlertTone.urgent
        ? SgColors.emergency
        : SgColors.navy900;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(SgRadius.card),
        boxShadow: SgShadows.card,
      ),
      child: Row(
        children: [
          SgIcon(icon, size: 20, color: Colors.white),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              message,
              style: SgType.captionMedium.copyWith(color: Colors.white),
            ),
          ),
          if (onDismiss != null)
            GestureDetector(
              onTap: onDismiss,
              behavior: HitTestBehavior.opaque,
              child: const Padding(
                padding: EdgeInsets.only(left: 8),
                child: SgIcon('x', size: 16, color: Colors.white70),
              ),
            ),
        ],
      ),
    );
  }
}

/// Calm spinner + label for "Request submitting…" (brief §16). Never a skeleton.
class SgLoadingState extends StatelessWidget {
  const SgLoadingState({super.key, required this.label});
  final String label;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 40, horizontal: 20),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          SizedBox(
            width: 34,
            height: 34,
            child: CircularProgressIndicator(
              strokeWidth: 3,
              valueColor: const AlwaysStoppedAnimation(SgColors.emergency),
              backgroundColor: SgColors.borderHairline,
            ),
          ),
          const SizedBox(height: 16),
          Text(
            label,
            textAlign: TextAlign.center,
            style: SgType.bodyMedium.copyWith(color: SgColors.textSecondary),
          ),
        ],
      ),
    );
  }
}

/// Calm empty/placeholder — "No responder assigned yet". Truthful, short copy.
class SgEmptyState extends StatelessWidget {
  const SgEmptyState({
    super.key,
    required this.title,
    this.icon = 'clock',
    this.description,
    this.action,
  });

  final String title;
  final String icon;
  final String? description;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 36, horizontal: 24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 52,
            height: 52,
            decoration: const BoxDecoration(
              color: SgColors.bgSunken,
              shape: BoxShape.circle,
            ),
            child: Center(
              child: SgIcon(icon, size: 24, color: SgColors.textMuted),
            ),
          ),
          const SizedBox(height: 12),
          Text(
            title,
            textAlign: TextAlign.center,
            style: SgType.cardHeading.copyWith(
              color: SgColors.textPrimary,
              fontWeight: FontWeight.w600,
            ),
          ),
          if (description != null) ...[
            const SizedBox(height: 6),
            ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 260),
              child: Text(
                description!,
                textAlign: TextAlign.center,
                style: SgType.caption.copyWith(color: SgColors.textMuted),
              ),
            ),
          ],
          if (action != null) ...[const SizedBox(height: 16), action!],
        ],
      ),
    );
  }
}
