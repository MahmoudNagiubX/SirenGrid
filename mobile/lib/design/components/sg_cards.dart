import 'package:flutter/material.dart';

import '../sg_icon.dart';
import '../tokens.dart';
import 'sg_feedback.dart';

/// One of the four Home service choices. Selected = red icon tile + 2px red
/// border + soft red glow; resting = navy icon tile on white. The icon carries
/// the emphasis; the label stays navy + bold in both states.
class SgServiceCard extends StatefulWidget {
  const SgServiceCard({
    super.key,
    required this.icon,
    required this.label,
    required this.selected,
    this.onTap,
  });

  final String icon;
  final String label;
  final bool selected;
  final VoidCallback? onTap;

  @override
  State<SgServiceCard> createState() => _SgServiceCardState();
}

class _SgServiceCardState extends State<SgServiceCard> {
  bool _down = false;

  @override
  Widget build(BuildContext context) {
    final sel = widget.selected;
    return GestureDetector(
      onTapDown: (_) => setState(() => _down = true),
      onTapUp: (_) => setState(() => _down = false),
      onTapCancel: () => setState(() => _down = false),
      onTap: widget.onTap,
      child: AnimatedScale(
        scale: _down ? 0.965 : 1,
        duration: SgDur.fast,
        child: AnimatedContainer(
          duration: SgDur.base,
          curve: SgDur.easeStandard,
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 16),
          decoration: BoxDecoration(
            color: sel ? SgColors.emergencySoft : SgColors.bgSurface,
            borderRadius: BorderRadius.circular(SgRadius.card),
            border: Border.all(
              color: sel ? SgColors.emergency : SgColors.borderHairline,
              width: 2,
            ),
            boxShadow: sel
                ? const [
                    BoxShadow(
                      color: Color(0x2ED90429),
                      blurRadius: 22,
                      offset: Offset(0, 8),
                    ),
                  ]
                : SgShadows.xs,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              AnimatedContainer(
                duration: SgDur.base,
                width: 46,
                height: 46,
                decoration: BoxDecoration(
                  color: sel ? null : SgColors.navy900,
                  gradient: sel ? SgColors.gradientEmergency : null,
                  borderRadius: BorderRadius.circular(16),
                  boxShadow: sel
                      ? const [
                          BoxShadow(
                            color: Color(0x57D90429),
                            blurRadius: 14,
                            offset: Offset(0, 6),
                          ),
                        ]
                      : null,
                ),
                child: Center(
                  child: SgIcon(
                    widget.icon,
                    size: 25,
                    color: Colors.white,
                    strokeWidth: 2.1,
                  ),
                ),
              ),
              const SizedBox(height: 12),
              Flexible(
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Flexible(
                      child: Text(
                        widget.label,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: SgType.cardHeading.copyWith(
                          color: SgColors.heading,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                    if (sel)
                      Container(
                        width: 9,
                        height: 9,
                        decoration: const BoxDecoration(
                          color: SgColors.emergency,
                          shape: BoxShape.circle,
                        ),
                      ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Generic white content card — icon + title + supporting line + trailing slot.
class SgInfoCard extends StatelessWidget {
  const SgInfoCard({
    super.key,
    required this.title,
    this.icon,
    this.description,
    this.trailing,
    this.tone = SgChipTone.neutral,
  });

  final String title;
  final String? icon;
  final String? description;
  final Widget? trailing;
  final SgChipTone tone;

  @override
  Widget build(BuildContext context) {
    final tileBg = tone == SgChipTone.info
        ? SgColors.infoSoft
        : SgColors.bgSunken;
    final tileFg = tone == SgChipTone.info
        ? SgColors.infoStrong
        : SgColors.navy900;
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: SgColors.bgSurface,
        borderRadius: BorderRadius.circular(SgRadius.card),
        border: Border.all(color: SgColors.borderHairline),
        boxShadow: SgShadows.card,
      ),
      child: Row(
        children: [
          if (icon != null) ...[
            Container(
              width: 42,
              height: 42,
              decoration: BoxDecoration(
                color: tileBg,
                borderRadius: BorderRadius.circular(SgRadius.control),
              ),
              child: Center(child: SgIcon(icon!, size: 20, color: tileFg)),
            ),
            const SizedBox(width: 14),
          ],
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: SgType.bodyMedium.copyWith(
                    color: SgColors.textPrimary,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                if (description != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 3),
                    child: Text(
                      description!,
                      style: SgType.caption.copyWith(color: SgColors.textMuted),
                    ),
                  ),
              ],
            ),
          ),
          ?trailing,
        ],
      ),
    );
  }
}

enum SgLocationCardState {
  ready,
  permissionRequired,
  servicesOff,
  locating,
  blocked,
}

/// Current-location readiness card near the emergency CTA on Home.
class SgLocationCard extends StatelessWidget {
  const SgLocationCard({
    super.key,
    required this.title,
    this.state = SgLocationCardState.ready,
    this.address,
    this.actionLabel = 'Retry',
    this.onAction,
  });

  final String title;
  final SgLocationCardState state;
  final String? address;
  final String actionLabel;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    final tone = switch (state) {
      SgLocationCardState.ready => SgColors.infoStrong,
      SgLocationCardState.locating => SgColors.textMuted,
      _ => SgColors.emergencyHover,
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      decoration: BoxDecoration(
        color: SgColors.bgSurface,
        borderRadius: BorderRadius.circular(SgRadius.card),
        border: Border.all(color: SgColors.borderHairline),
        boxShadow: SgShadows.xs,
      ),
      child: Row(
        children: [
          SgIcon('map-pin', size: 20, color: tone),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: SgType.captionMedium.copyWith(
                    color: tone,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                if (address != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 2),
                    child: Text(
                      address!,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: SgType.caption.copyWith(color: SgColors.textMuted),
                    ),
                  ),
              ],
            ),
          ),
          if (state != SgLocationCardState.ready &&
              state != SgLocationCardState.locating &&
              onAction != null)
            GestureDetector(
              onTap: onAction,
              child: Container(
                height: 32,
                padding: const EdgeInsets.symmetric(horizontal: 12),
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: SgColors.navy900,
                  borderRadius: BorderRadius.circular(SgRadius.pill),
                ),
                child: Text(
                  actionLabel,
                  style: SgType.captionMedium.copyWith(
                    color: Colors.white,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// The floating bottom card on Live Response Tracking — responder unit, big ETA,
/// status chip, freshness line and a compact step timeline. Never exposes
/// planner-internal detail (brief §15).
class SgResponderCard extends StatelessWidget {
  const SgResponderCard({
    super.key,
    required this.label,
    required this.icon,
    required this.statusLabel,
    required this.steps,
    required this.activeStep,
    this.eta,
    this.freshnessLabel,
    this.stale = false,
    this.provenanceLabel,
  });

  final String label;
  final String icon;
  final String statusLabel;
  final List<String> steps;
  final int activeStep;
  final String? eta;
  final String? freshnessLabel;
  final bool stale;
  final String? provenanceLabel;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(22, 18, 22, 24),
      decoration: const BoxDecoration(
        color: SgColors.bgSurface,
        borderRadius: BorderRadius.vertical(
          top: Radius.circular(SgRadius.sheet),
        ),
        boxShadow: SgShadows.sheet,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Center(
            child: Container(
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                color: SgColors.borderStrong,
                borderRadius: BorderRadius.circular(SgRadius.pill),
              ),
            ),
          ),
          const SizedBox(height: 16),
          Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Container(
                width: 46,
                height: 46,
                decoration: BoxDecoration(
                  color: SgColors.navy900,
                  borderRadius: BorderRadius.circular(15),
                ),
                child: Center(
                  child: SgIcon(
                    icon,
                    size: 23,
                    color: Colors.white,
                    strokeWidth: 2.1,
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      label,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: SgType.cardHeading.copyWith(
                        color: SgColors.heading,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    if (freshnessLabel != null)
                      Padding(
                        padding: const EdgeInsets.only(top: 3),
                        child: Row(
                          children: [
                            Container(
                              width: 6,
                              height: 6,
                              decoration: BoxDecoration(
                                shape: BoxShape.circle,
                                color: stale
                                    ? SgColors.emergency
                                    : SgColors.infoStrong,
                              ),
                            ),
                            const SizedBox(width: 6),
                            Flexible(
                              child: Text(
                                freshnessLabel!,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: SgType.caption.copyWith(
                                  color: stale
                                      ? SgColors.emergencyHover
                                      : SgColors.textMuted,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    eta ?? '—',
                    style: const TextStyle(
                      fontSize: 34,
                      height: 38 / 34,
                      fontWeight: FontWeight.w700,
                      letterSpacing: -0.68,
                      color: SgColors.heading,
                    ),
                  ),
                  const SizedBox(height: 4),
                  SgStatusChip(
                    statusLabel,
                    tone: SgChipTone.urgent,
                    pulsing: true,
                  ),
                ],
              ),
            ],
          ),
          if (provenanceLabel != null)
            Padding(
              padding: const EdgeInsets.only(top: 12),
              child: Align(
                alignment: AlignmentDirectional.centerStart,
                child: SgStatusChip(
                  provenanceLabel!,
                  tone: SgChipTone.neutral,
                  dot: false,
                ),
              ),
            ),
          const SizedBox(height: 22),
          _Timeline(steps: steps, activeStep: activeStep),
        ],
      ),
    );
  }
}

class _Timeline extends StatelessWidget {
  const _Timeline({required this.steps, required this.activeStep});
  final List<String> steps;
  final int activeStep;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Row(
          children: [
            for (var i = 0; i < steps.length; i++) ...[
              Container(
                width: i == activeStep ? 13 : 10,
                height: i == activeStep ? 13 : 10,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: i < activeStep
                      ? SgColors.navy900
                      : i == activeStep
                      ? SgColors.emergency
                      : SgColors.borderStrong,
                  boxShadow: i == activeStep
                      ? const [
                          BoxShadow(
                            color: SgColors.emergencySoft,
                            blurRadius: 0,
                            spreadRadius: 4,
                          ),
                        ]
                      : null,
                ),
              ),
              if (i < steps.length - 1)
                Expanded(
                  child: Container(
                    height: 3,
                    margin: const EdgeInsets.symmetric(horizontal: 2),
                    decoration: BoxDecoration(
                      color: i < activeStep
                          ? SgColors.navy900
                          : SgColors.borderHairline,
                      borderRadius: BorderRadius.circular(2),
                    ),
                  ),
                ),
            ],
          ],
        ),
        const SizedBox(height: 9),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            for (var i = 0; i < steps.length; i++)
              SizedBox(
                width: 72,
                child: Text(
                  steps[i],
                  textAlign: i == 0
                      ? TextAlign.start
                      : i == steps.length - 1
                      ? TextAlign.end
                      : TextAlign.center,
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: i == activeStep
                        ? FontWeight.w700
                        : FontWeight.w500,
                    color: i == activeStep
                        ? SgColors.emergencyHover
                        : i < activeStep
                        ? SgColors.textSecondary
                        : SgColors.textMuted,
                  ),
                ),
              ),
          ],
        ),
      ],
    );
  }
}
