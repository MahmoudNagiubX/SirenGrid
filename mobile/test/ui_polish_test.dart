import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:sirengrid_citizen/design/components/sg_buttons.dart';
import 'package:sirengrid_citizen/design/components/sg_cards.dart';
import 'package:sirengrid_citizen/design/components/sg_forms.dart';
import 'package:sirengrid_citizen/design/sg_icon.dart';
import 'package:sirengrid_citizen/design/theme.dart';
import 'package:sirengrid_citizen/features/auth/citizen_profile.dart';
import 'package:sirengrid_citizen/l10n/strings.dart';

Widget _host(Widget child) => MaterialApp(
  theme: sgTheme(),
  supportedLocales: SgStrings.supportedLocales,
  home: Scaffold(body: Center(child: child)),
);

Finder _iconNamed(String name) =>
    find.byWidgetPredicate((w) => w is SgIcon && w.name == name);

void main() {
  setUpAll(() => GoogleFonts.config.allowRuntimeFetching = false);

  group('identity status is humanized for display', () {
    CitizenProfile profile(String status) => CitizenProfile(
      citizenReference: 'demo-citizen-001',
      displayName: 'Sara Ahmed',
      phone: '01000000000',
      registeredAddress: '12 Nile St, Cairo',
      nationalIdMasked: '•••••••••1234',
      identityStatus: status,
    );

    test('DEMO_VERIFIED -> "Demo verified"', () {
      expect(profile('DEMO_VERIFIED').identityStatusLabel, 'Demo verified');
    });

    test('single token is title-cased', () {
      expect(profile('verified').identityStatusLabel, 'Verified');
    });

    test('empty passes through untouched', () {
      expect(profile('').identityStatusLabel, '');
    });
  });

  testWidgets('PIN field trailing control is an eye toggle, not a shield', (
    tester,
  ) async {
    final controller = TextEditingController();
    await tester.pumpWidget(
      _host(
        SizedBox(
          width: 320,
          child: SgTextField(
            label: 'PIN',
            controller: controller,
            icon: 'shield',
            obscure: true,
          ),
        ),
      ),
    );

    expect(_iconNamed('eye'), findsOneWidget);
    expect(_iconNamed('eye-off'), findsNothing);
    expect(_iconNamed('shield-check'), findsNothing);

    await tester.tap(find.bySemanticsLabel('Show PIN'));
    await tester.pump();

    expect(_iconNamed('eye-off'), findsOneWidget);
    expect(_iconNamed('eye'), findsNothing);
  });

  testWidgets('service card fits its Home grid cell without overflow', (
    tester,
  ) async {
    // The exact cell Home's GridView hands each card on a compact phone:
    // (392.7 - 44 page padding - 12 gap) / 2 wide, 138 tall (mainAxisExtent).
    await tester.pumpWidget(
      _host(
        const SizedBox(
          width: 168,
          height: 138,
          child: SgServiceCard(
            icon: 'ambulance',
            label: 'Ambulance',
            selected: true,
          ),
        ),
      ),
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('confirmation Cancel + "Confirm request" fit the sheet row', (
    tester,
  ) async {
    // Sheet inner width on a compact phone: 392.7 - 44 (22px each side).
    await tester.pumpWidget(
      _host(
        const SizedBox(
          width: 348,
          child: Row(
            children: [
              Expanded(
                flex: 2,
                child: SgSecondaryButton(label: 'Cancel', full: true),
              ),
              SizedBox(width: 10),
              Expanded(
                flex: 3,
                child: SgEmergencyButton(label: 'Confirm request', full: true),
              ),
            ],
          ),
        ),
      ),
    );
    expect(tester.takeException(), isNull);

    // The CTA label renders in one un-truncated piece: no ellipsis, and it is
    // wrapped in a scale-down FittedBox so a tight row shrinks the glyphs a
    // hair instead of clipping to "Confirm req…".
    expect(find.text('Confirm request'), findsOneWidget);
    expect(find.text('Cancel'), findsOneWidget);
    final label = tester.widget<Text>(find.text('Confirm request'));
    expect(label.overflow, isNot(TextOverflow.ellipsis));
    expect(
      find.ancestor(
        of: find.text('Confirm request'),
        matching: find.byType(FittedBox),
      ),
      findsOneWidget,
    );
  });
}
