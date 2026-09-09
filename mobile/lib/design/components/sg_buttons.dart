import 'package:flutter/material.dart';

import '../sg_icon.dart';
import '../tokens.dart';

enum SgButtonSize { sm, md, lg }

double _height(SgButtonSize s) => switch (s) {
  SgButtonSize.sm => 40,
  SgButtonSize.md => 52,
  SgButtonSize.lg => 58,
};

TextStyle _label(SgButtonSize s) => switch (s) {
  SgButtonSize.sm => SgType.captionMedium.copyWith(fontWeight: FontWeight.w600),
  SgButtonSize.md => SgType.bodyMedium.copyWith(fontWeight: FontWeight.w600),
  SgButtonSize.lg => SgType.cardHeading,
};

/// Press-scale wrapper (0.965–0.97, brief §hover/press — the system is touch-first).
class _Pressable extends StatefulWidget {
  const _Pressable({
    required this.child,
    required this.onTap,
    this.scale = 0.97,
    this.enabled = true,
  });
  final Widget child;
  final VoidCallback? onTap;
  final double scale;
  final bool enabled;

  @override
  State<_Pressable> createState() => _PressableState();
}

class _PressableState extends State<_Pressable> {
  bool _down = false;

  @override
  Widget build(BuildContext context) {
    final active = widget.enabled && widget.onTap != null;
    return GestureDetector(
      onTapDown: active ? (_) => setState(() => _down = true) : null,
      onTapUp: active ? (_) => setState(() => _down = false) : null,
      onTapCancel: active ? () => setState(() => _down = false) : null,
      onTap: active ? widget.onTap : null,
      child: AnimatedScale(
        scale: _down ? widget.scale : 1,
        duration: SgDur.fast,
        curve: SgDur.easeStandard,
        child: widget.child,
      ),
    );
  }
}

class _Spinner extends StatefulWidget {
  const _Spinner({required this.color, this.size = 18, this.stroke = 2.5});
  final Color color;
  final double size;
  final double stroke;
  @override
  State<_Spinner> createState() => _SpinnerState();
}

class _SpinnerState extends State<_Spinner>
    with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 700),
  )..repeat();
  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => SizedBox(
    width: widget.size,
    height: widget.size,
    child: CircularProgressIndicator(
      strokeWidth: widget.stroke,
      valueColor: AlwaysStoppedAnimation(widget.color),
      backgroundColor: widget.color.withValues(alpha: 0.35),
    ),
  );
}

/// Navy-filled default action verb (Login, confirmation, account). Emergency red
/// is reserved for [SgEmergencyButton].
class SgPrimaryButton extends StatelessWidget {
  const SgPrimaryButton({
    super.key,
    required this.label,
    this.onPressed,
    this.size = SgButtonSize.md,
    this.icon,
    this.loading = false,
    this.full = false,
  });

  final String label;
  final VoidCallback? onPressed;
  final SgButtonSize size;
  final String? icon;
  final bool loading;
  final bool full;

  @override
  Widget build(BuildContext context) {
    final disabled = onPressed == null;
    final child = Container(
      height: _height(size),
      width: full ? double.infinity : null,
      padding: EdgeInsets.symmetric(
        horizontal: size == SgButtonSize.lg ? 24 : 20,
      ),
      decoration: BoxDecoration(
        color: SgColors.navy900,
        borderRadius: BorderRadius.circular(SgRadius.control),
        boxShadow: disabled ? null : SgShadows.xs,
      ),
      child: Opacity(
        opacity: disabled && !loading ? 0.42 : 1,
        child: Row(
          mainAxisSize: full ? MainAxisSize.max : MainAxisSize.min,
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            if (loading)
              const _Spinner(color: Colors.white, size: 16, stroke: 2)
            else if (icon != null) ...[
              SgIcon(icon!, size: 18, color: Colors.white, strokeWidth: 2.1),
              const SizedBox(width: 8),
            ],
            if (!loading)
              Flexible(
                child: Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: _label(size).copyWith(color: Colors.white),
                ),
              ),
          ],
        ),
      ),
    );
    return _Pressable(
      onTap: loading ? null : onPressed,
      enabled: !disabled,
      child: child,
    );
  }
}

/// Outline secondary action, always beside a primary/emergency action.
class SgSecondaryButton extends StatelessWidget {
  const SgSecondaryButton({
    super.key,
    required this.label,
    this.onPressed,
    this.size = SgButtonSize.md,
    this.icon,
    this.full = false,
  });

  final String label;
  final VoidCallback? onPressed;
  final SgButtonSize size;
  final String? icon;
  final bool full;

  @override
  Widget build(BuildContext context) {
    final disabled = onPressed == null;
    final child = Container(
      height: _height(size),
      width: full ? double.infinity : null,
      padding: EdgeInsets.symmetric(
        horizontal: size == SgButtonSize.lg ? 24 : 20,
      ),
      decoration: BoxDecoration(
        color: SgColors.bgSurface,
        borderRadius: BorderRadius.circular(SgRadius.control),
        border: Border.all(color: SgColors.borderStrong, width: 1.5),
      ),
      child: Opacity(
        opacity: disabled ? 0.42 : 1,
        child: Row(
          mainAxisSize: full ? MainAxisSize.max : MainAxisSize.min,
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            if (icon != null) ...[
              SgIcon(icon!, size: 17, color: SgColors.textPrimary),
              const SizedBox(width: 8),
            ],
            Flexible(
              child: Text(
                label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: _label(size).copyWith(color: SgColors.textPrimary),
              ),
            ),
          ],
        ),
      ),
    );
    return _Pressable(onTap: onPressed, enabled: !disabled, child: child);
  }
}

/// The emergency-red CTA. Pill for the Home CTA / confirmation; circle for SOS.
/// 2-stop red gradient + layered red glow (brief §10), optional pulse ring.
class SgEmergencyButton extends StatefulWidget {
  const SgEmergencyButton({
    super.key,
    required this.label,
    this.onPressed,
    this.icon,
    this.pulsing = false,
    this.loading = false,
    this.full = false,
    this.shape = SgEmergencyShape.pill,
  });

  final String label;
  final VoidCallback? onPressed;
  final String? icon;
  final bool pulsing;
  final bool loading;
  final bool full;
  final SgEmergencyShape shape;

  @override
  State<SgEmergencyButton> createState() => _SgEmergencyButtonState();
}

enum SgEmergencyShape { pill, circle }

class _SgEmergencyButtonState extends State<SgEmergencyButton>
    with SingleTickerProviderStateMixin {
  late final AnimationController _pulse = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 2400),
  );
  bool _down = false;

  @override
  void initState() {
    super.initState();
    if (widget.pulsing) _pulse.repeat();
  }

  @override
  void didUpdateWidget(covariant SgEmergencyButton old) {
    super.didUpdateWidget(old);
    if (widget.pulsing && !_pulse.isAnimating) {
      _pulse.repeat();
    } else if (!widget.pulsing && _pulse.isAnimating) {
      _pulse.stop();
    }
  }

  @override
  void dispose() {
    _pulse.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isCircle = widget.shape == SgEmergencyShape.circle;
    final disabled = widget.onPressed == null;
    final radius = isCircle
        ? BorderRadius.circular(999)
        : BorderRadius.circular(SgRadius.pill);
    final reduceMotion = MediaQuery.maybeDisableAnimationsOf(context) ?? false;

    Widget core = Container(
      height: isCircle ? 96 : 60,
      width: isCircle ? 96 : (widget.full ? double.infinity : null),
      padding: isCircle
          ? EdgeInsets.zero
          : EdgeInsets.symmetric(horizontal: widget.full ? 18 : 28),
      decoration: BoxDecoration(
        gradient: SgColors.gradientEmergency,
        borderRadius: radius,
        boxShadow: _down ? SgShadows.ctaGlow : SgShadows.emergencyStrong,
      ),
      child: Opacity(
        opacity: disabled && !widget.loading ? 0.5 : 1,
        child: Row(
          mainAxisSize: widget.full && !isCircle
              ? MainAxisSize.max
              : MainAxisSize.min,
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            if (widget.loading)
              const _Spinner(color: Colors.white)
            else ...[
              if (widget.icon != null) ...[
                SgIcon(
                  widget.icon!,
                  size: 20,
                  color: Colors.white,
                  strokeWidth: 2.2,
                ),
                const SizedBox(width: 10),
              ],
              Flexible(
                child: FittedBox(
                  fit: BoxFit.scaleDown,
                  child: Text(
                    widget.label,
                    maxLines: 1,
                    softWrap: false,
                    style: SgType.cardHeading.copyWith(
                      color: Colors.white,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );

    if (widget.pulsing && !reduceMotion) {
      core = Stack(
        clipBehavior: Clip.none,
        alignment: Alignment.center,
        children: [
          AnimatedBuilder(
            animation: _pulse,
            builder: (context, _) {
              final v = _pulse.value;
              return Positioned.fill(
                left: -6,
                right: -6,
                top: -6,
                bottom: -6,
                child: Opacity(
                  opacity: (1 - v) * 0.55,
                  child: Transform.scale(
                    scale: 1 + v * 0.22,
                    child: Container(
                      decoration: BoxDecoration(
                        borderRadius: radius,
                        border: Border.all(color: SgColors.emergency, width: 2),
                      ),
                    ),
                  ),
                ),
              );
            },
          ),
          core,
        ],
      );
    }

    return _Pressable(
      onTap: widget.loading ? null : widget.onPressed,
      enabled: !disabled,
      scale: 0.965,
      child: Listener(
        onPointerDown: disabled ? null : (_) => setState(() => _down = true),
        onPointerUp: (_) => setState(() => _down = false),
        onPointerCancel: (_) => setState(() => _down = false),
        child: core,
      ),
    );
  }
}
