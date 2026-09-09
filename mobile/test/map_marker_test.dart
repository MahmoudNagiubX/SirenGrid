import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:sirengrid_citizen/design/components/sg_markers.dart';

/// TASK 01 — geo-anchor drift.
///
/// The drift bug was a fixed *screen-pixel* offset between the anchored point
/// and the visible dot (label pill + caret stacked above it, plus a
/// bottom-anchored oversized box). A constant pixel offset reads as a
/// zoom-dependent geographic error. The fix: the dot is the exact centre of the
/// marker box, and the `flutter_map` `Marker` anchors at `Alignment.center`.
///
/// This test locks the invariant the map relies on: whatever the label/pulse
/// do, the red dot's centre equals the marker box's centre. If that holds, a
/// centre-anchored Marker keeps the dot welded to its LatLng at every zoom.
void main() {
  setUpAll(() => GoogleFonts.config.allowRuntimeFetching = false);

  testWidgets('SgMapPin dot is centred in its box (with label + pulse)', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Center(
            child: SizedBox.fromSize(
              size: SgMapPin.size,
              child: const SgMapPin(label: 'You are here'),
            ),
          ),
        ),
      ),
    );
    await tester.pump(const Duration(milliseconds: 300));

    final box = tester.getRect(find.byType(SgMapPin));
    // The 22x22 red dot is the smallest Container; find it by size.
    final dot = find.byWidgetPredicate((w) {
      if (w is! Container) return false;
      final c = w.constraints;
      return c != null && c.maxWidth == 22 && c.maxHeight == 22;
    });
    expect(dot, findsOneWidget);

    final dotCentre = tester.getCenter(dot);
    expect((dotCentre.dx - box.center.dx).abs(), lessThan(0.5));
    expect((dotCentre.dy - box.center.dy).abs(), lessThan(0.5));
  });

  testWidgets('SgMapPin without a label still centres the dot', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Center(
            child: SizedBox.fromSize(
              size: SgMapPin.size,
              child: const SgMapPin(pulsing: false),
            ),
          ),
        ),
      ),
    );

    final box = tester.getRect(find.byType(SgMapPin));
    final dot = find.byWidgetPredicate((w) {
      if (w is! Container) return false;
      final c = w.constraints;
      return c != null && c.maxWidth == 22 && c.maxHeight == 22;
    });
    final dotCentre = tester.getCenter(dot);
    expect((dotCentre.dx - box.center.dx).abs(), lessThan(0.5));
    expect((dotCentre.dy - box.center.dy).abs(), lessThan(0.5));
  });
}
