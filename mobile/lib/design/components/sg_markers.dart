import 'package:flutter/material.dart';

import '../sg_icon.dart';
import '../tokens.dart';

/// The citizen's own location — flat emergency-red dot, white casing, soft red
/// halo, optional label pill with caret. Deliberately the opposite of the
/// responder marker (navy + glyph) so the two never read as the same thing.
class SgMapPin extends StatefulWidget {
  const SgMapPin({super.key, this.label, this.pulsing = true});

  final String? label;
  final bool pulsing;

  /// Rendered size of the whole marker widget (for `flutter_map` anchoring).
  static const Size size = Size(140, 78);

  @override
  State<SgMapPin> createState() => _SgMapPinState();
}

class _SgMapPinState extends State<SgMapPin>
    with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 2600),
  );

  @override
  void initState() {
    super.initState();
    if (widget.pulsing) _c.repeat();
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final reduceMotion = MediaQuery.maybeDisableAnimationsOf(context) ?? false;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (widget.label != null) ...[
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 5),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(SgRadius.pill),
              boxShadow: SgShadows.card,
            ),
            child: Text(
              widget.label!.toUpperCase(),
              style: SgType.chip.copyWith(color: SgColors.heading),
            ),
          ),
          CustomPaint(size: const Size(10, 5), painter: _CaretPainter()),
          const SizedBox(height: 2),
        ],
        SizedBox(
          width: 44,
          height: 44,
          child: Stack(
            alignment: Alignment.center,
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: const BoxDecoration(
                  color: Color(0x29EF233C),
                  shape: BoxShape.circle,
                ),
              ),
              if (widget.pulsing && !reduceMotion)
                AnimatedBuilder(
                  animation: _c,
                  builder: (context, _) => Opacity(
                    opacity: (1 - _c.value) * 0.8,
                    child: Transform.scale(
                      scale: 0.75 + _c.value * 0.95,
                      child: Container(
                        width: 44,
                        height: 44,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          border: Border.all(
                            color: SgColors.emergency,
                            width: 2,
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              Container(
                width: 22,
                height: 22,
                decoration: BoxDecoration(
                  color: SgColors.mapCitizenPin,
                  shape: BoxShape.circle,
                  border: Border.all(color: Colors.white, width: 4),
                  boxShadow: SgShadows.marker,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _CaretPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final p = Paint()..color = Colors.white;
    final path = Path()
      ..moveTo(0, 0)
      ..lineTo(size.width, 0)
      ..lineTo(size.width / 2, size.height)
      ..close();
    canvas.drawPath(path, p);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

/// The responder's marker — white circular casing, navy body, service glyph,
/// optional heading indicator + pulse ring when active (brief §14).
class SgResponderMarker extends StatefulWidget {
  const SgResponderMarker({
    super.key,
    this.icon = 'ambulance',
    this.selected = true,
    this.headingDegrees,
  });

  final String icon;
  final bool selected;
  final double? headingDegrees;

  static const Size size = Size(66, 66);

  @override
  State<SgResponderMarker> createState() => _SgResponderMarkerState();
}

class _SgResponderMarkerState extends State<SgResponderMarker>
    with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 2400),
  );

  @override
  void initState() {
    super.initState();
    if (widget.selected) _c.repeat();
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final reduceMotion = MediaQuery.maybeDisableAnimationsOf(context) ?? false;
    return SizedBox(
      width: 66,
      height: 66,
      child: Stack(
        alignment: Alignment.center,
        clipBehavior: Clip.none,
        children: [
          if (widget.selected)
            Container(
              width: 66,
              height: 66,
              decoration: const BoxDecoration(
                color: Color(0x24395886),
                shape: BoxShape.circle,
              ),
            ),
          if (widget.selected && !reduceMotion)
            AnimatedBuilder(
              animation: _c,
              builder: (context, _) => Opacity(
                opacity: (1 - _c.value) * 0.85,
                child: Transform.scale(
                  scale: 0.8 + _c.value * 0.95,
                  child: Container(
                    width: 66,
                    height: 66,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      border: Border.all(color: SgColors.mapRoute, width: 2),
                    ),
                  ),
                ),
              ),
            ),
          if (widget.selected && widget.headingDegrees != null)
            Transform.rotate(
              angle: widget.headingDegrees! * 3.1415926 / 180,
              child: Transform.translate(
                offset: const Offset(0, -33),
                child: CustomPaint(
                  size: const Size(10, 8),
                  painter: _HeadingPainter(),
                ),
              ),
            ),
          Container(
            width: 46,
            height: 46,
            decoration: const BoxDecoration(
              color: Colors.white,
              shape: BoxShape.circle,
              boxShadow: SgShadows.marker,
            ),
            child: Center(
              child: Container(
                width: 36,
                height: 36,
                decoration: const BoxDecoration(
                  color: SgColors.navy900,
                  shape: BoxShape.circle,
                ),
                child: Center(
                  child: SgIcon(
                    widget.icon,
                    size: 19,
                    color: Colors.white,
                    strokeWidth: 2.1,
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _HeadingPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final p = Paint()..color = SgColors.mapRoute;
    final path = Path()
      ..moveTo(size.width / 2, 0)
      ..lineTo(size.width, size.height)
      ..lineTo(0, size.height)
      ..close();
    canvas.drawPath(path, p);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
