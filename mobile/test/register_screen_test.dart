import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:sirengrid_citizen/core/api_client.dart';
import 'package:sirengrid_citizen/core/location.dart';
import 'package:sirengrid_citizen/core/storage.dart';
import 'package:sirengrid_citizen/design/theme.dart';
import 'package:sirengrid_citizen/features/auth/auth_cubit.dart';
import 'package:sirengrid_citizen/features/auth/register_screen.dart';
import 'package:sirengrid_citizen/l10n/strings.dart';

import 'support.dart';

const _profileJson = {
  'citizen_reference': 'citizen-abc123def456',
  'display_name': 'New Citizen',
  'phone': '01111222333',
  'registered_address': '8 Test Street, Nasr City, Cairo',
  'national_id_masked': '**********3456',
  'identity_status': 'DEMO_VERIFIED',
};

final _submitBtn = find.byKey(const Key('register_submit'));

Widget _host(
  AuthCubit auth, {
  LocationService? location,
  Future<String?> Function()? captureIdImage,
  Future<Map<String, dynamic>> Function(String)? scanIdImage,
  Future<void> Function(String)? discardIdImage,
  Locale? locale,
}) => MaterialApp(
  theme: sgTheme(),
  locale: locale,
  supportedLocales: SgStrings.supportedLocales,
  localizationsDelegates: const [
    GlobalMaterialLocalizations.delegate,
    GlobalWidgetsLocalizations.delegate,
    GlobalCupertinoLocalizations.delegate,
  ],
  home: BlocProvider<AuthCubit>.value(
    value: auth,
    child: RegisterScreen(
      locationService: location,
      captureIdImage: captureIdImage,
      scanIdImage: scanIdImage,
      discardIdImage: discardIdImage ?? (_) async {},
    ),
  ),
);

Future<void> _openManual(WidgetTester tester) async {
  await tester.tap(find.text('Enter details manually'));
  await tester.pump();
}

Future<void> _fillValid(WidgetTester tester) async {
  await tester.enterText(find.byType(TextField).at(0), 'New Citizen');
  await tester.enterText(find.byType(TextField).at(1), '29001010123456');
  await tester.enterText(
    find.byType(TextField).at(2),
    '8 Test Street, Nasr City, Cairo',
  );
  await tester.enterText(find.byType(TextField).at(3), '01111222333');
  await tester.enterText(find.byType(TextField).at(4), '4321');
  await tester.enterText(find.byType(TextField).at(5), '4321');
  await tester.pump();
}

Future<Map<String, dynamic>> _registerBody(ScriptedClient client) async =>
    client.bodyOf(
      client.requests.firstWhere((r) => r.url.path.endsWith('/auth/register')),
    );

void main() {
  setUpAll(() => GoogleFonts.config.allowRuntimeFetching = false);
  setUp(() => SecureStore.useInMemory());
  tearDown(() async {
    SecureStore.reset();
  });

  // A tall surface so the whole form is on-screen and taps never miss.
  Future<void> pump(WidgetTester tester, Widget w) async {
    await tester.binding.setSurfaceSize(const Size(520, 1600));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(w);
  }

  testWidgets('renders scan-first CTA and permanent manual fallback', (
    tester,
  ) async {
    final auth = AuthCubit(ApiClient(client: ScriptedClient()));
    await pump(tester, _host(auth));

    expect(find.byKey(const Key('register_screen')), findsOneWidget);
    expect(find.text('Scan National ID'), findsOneWidget);
    expect(find.textContaining('OCR-assisted'), findsOneWidget);
    expect(find.text('Scan ID'), findsOneWidget);
    expect(find.text('Enter details manually'), findsOneWidget);
    expect(find.text('Full name'), findsNothing);

    await _openManual(tester);
    expect(find.text('Full name'), findsOneWidget);
    expect(find.text('National ID'), findsOneWidget);
    expect(find.text('Confirm PIN'), findsOneWidget);
    expect(find.text('Registered address'), findsOneWidget);
    expect(find.text('Use current location'), findsOneWidget);
    expect(_submitBtn, findsOneWidget);
    await auth.close();
  });

  testWidgets('empty submit shows field errors and makes no network call', (
    tester,
  ) async {
    final client = ScriptedClient();
    final auth = AuthCubit(ApiClient(client: client));
    await pump(tester, _host(auth));

    await _openManual(tester);
    await tester.tap(_submitBtn);
    await tester.pump();

    expect(find.text('Enter your full name.'), findsOneWidget);
    expect(find.text('Enter a valid 14-digit National ID.'), findsOneWidget);
    expect(client.requests, isEmpty);
    await auth.close();
  });

  testWidgets('PIN mismatch is caught client-side', (tester) async {
    final client = ScriptedClient();
    final auth = AuthCubit(ApiClient(client: client));
    await pump(tester, _host(auth));

    await _openManual(tester);
    await _fillValid(tester);
    await tester.enterText(find.byType(TextField).at(5), '9999');
    await tester.tap(_submitBtn);
    await tester.pump();

    expect(find.text("PINs don't match."), findsOneWidget);
    expect(client.requests, isEmpty);
    await auth.close();
  });

  testWidgets('impossible National ID birth date is blocked client-side', (
    tester,
  ) async {
    final client = ScriptedClient();
    final auth = AuthCubit(ApiClient(client: client));
    await pump(tester, _host(auth));

    await _openManual(tester);
    await _fillValid(tester);
    await tester.enterText(find.byType(TextField).at(1), '29002300123456');
    await tester.tap(_submitBtn);
    await tester.pump();

    expect(find.text('Enter a valid 14-digit National ID.'), findsOneWidget);
    expect(client.requests, isEmpty);
    await auth.close();
  });

  testWidgets('valid submit posts a normalized body to /auth/register', (
    tester,
  ) async {
    final client = ScriptedClient()
      ..enqueue(201, {
        'access_token': 'tok-123',
        'token_type': 'bearer',
        'expires_at': DateTime.now().toIso8601String(),
        'profile': _profileJson,
      }, matchPathEndsWith: '/auth/register')
      ..enqueue(200, _profileJson, matchPathEndsWith: '/me');
    final auth = AuthCubit(ApiClient(client: client));
    await pump(tester, _host(auth));

    await _openManual(tester);
    await _fillValid(tester);
    await tester.tap(_submitBtn);
    await tester.pumpAndSettle();

    final body = await _registerBody(client);
    expect(body['display_name'], 'New Citizen');
    expect(body['phone'], '01111222333');
    expect(body['national_id'], '29001010123456');
    expect(body['pin'], '4321');
    expect(body['pin_confirm'], '4321');
    expect(body.containsKey('citizen_reference'), isFalse);
    expect(body.containsKey('registered_latitude'), isFalse);
    expect(auth.state, isA<Authenticated>());
    await auth.close();
  });

  testWidgets('Use current location adds registered coordinates to the body', (
    tester,
  ) async {
    final client = ScriptedClient()
      ..enqueue(201, {
        'access_token': 'tok-123',
        'token_type': 'bearer',
        'expires_at': DateTime.now().toIso8601String(),
        'profile': _profileJson,
      }, matchPathEndsWith: '/auth/register')
      ..enqueue(200, _profileJson, matchPathEndsWith: '/me');
    final auth = AuthCubit(ApiClient(client: client));
    final location = LocationService(FakeLocationPort());
    await pump(tester, _host(auth, location: location));

    await _openManual(tester);
    await _fillValid(tester);
    await tester.tap(find.text('Use current location'));
    await tester.pumpAndSettle();
    expect(find.text('Account location saved'), findsOneWidget);

    await tester.tap(_submitBtn);
    await tester.pumpAndSettle();

    final body = await _registerBody(client);
    expect(body['registered_latitude'], closeTo(30.0561, 0.0001));
    expect(body['registered_longitude'], closeTo(31.3452, 0.0001));
    await auth.close();
  });

  testWidgets('camera cancellation returns deliberate fallback actions', (
    tester,
  ) async {
    final auth = AuthCubit(ApiClient(client: ScriptedClient()));
    await pump(tester, _host(auth, captureIdImage: () async => null));

    await tester.tap(find.text('Scan ID'));
    await tester.pumpAndSettle();
    expect(find.text('Scan the front of your National ID'), findsOneWidget);
    await tester.tap(find.text('Open camera'));
    await tester.pumpAndSettle();

    expect(find.text('No photo was taken.'), findsOneWidget);
    expect(find.text('Retake photo'), findsOneWidget);
    expect(find.text('Enter details manually'), findsOneWidget);
    await auth.close();
  });

  testWidgets('scan success autofills editable identity fields', (
    tester,
  ) async {
    final auth = AuthCubit(ApiClient(client: ScriptedClient()));
    await pump(
      tester,
      _host(
        auth,
        captureIdImage: () async => 'synthetic-front.jpg',
        scanIdImage: (_) async => {
          'success': true,
          'extracted': {
            'full_name': 'OCR Citizen',
            'national_id': '29001010123456',
            'registered_address_text': 'OCR Address, Cairo',
            'birth_date': '1990-01-01',
            'governorate': 'Cairo',
            'gender': 'Male',
          },
          'warnings': <String>[],
          'identity_source': 'EGYPTIAN_ID_OCR_DEMO',
        },
      ),
    );

    await tester.tap(find.text('Scan ID'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Open camera'));
    await tester.pumpAndSettle();
    expect(find.text('Use photo'), findsOneWidget);
    await tester.tap(find.text('Use photo'));
    await tester.pumpAndSettle();

    expect(find.text('ID read successfully'), findsOneWidget);
    final fields = tester
        .widgetList<TextField>(find.byType(TextField))
        .toList();
    expect(fields[0].controller!.text, 'OCR Citizen');
    expect(fields[1].controller!.text, '29001010123456');
    expect(fields[2].controller!.text, 'OCR Address, Cairo');
    await tester.enterText(find.byType(TextField).at(0), 'Corrected Citizen');
    expect(fields[0].controller!.text, 'Corrected Citizen');
    await auth.close();
  });

  testWidgets('loading state is bounded and has truthful copy', (tester) async {
    final pending = Completer<Map<String, dynamic>>();
    final auth = AuthCubit(ApiClient(client: ScriptedClient()));
    await pump(
      tester,
      _host(
        auth,
        captureIdImage: () async => 'synthetic-front.jpg',
        scanIdImage: (_) => pending.future,
      ),
    );

    await tester.tap(find.text('Scan ID'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Open camera'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Use photo'));
    await tester.pump();
    expect(find.text('Reading your ID...'), findsOneWidget);
    expect(find.text('This can take a few seconds.'), findsOneWidget);

    pending.complete({
      'success': false,
      'code': 'TIMEOUT',
      'message': 'The scan timed out.',
      'extracted': null,
    });
    await tester.pumpAndSettle();
    expect(find.text('The scan timed out.'), findsOneWidget);
    await auth.close();
  });

  testWidgets('OCR failure still permits manual registration', (tester) async {
    final auth = AuthCubit(ApiClient(client: ScriptedClient()));
    await pump(
      tester,
      _host(
        auth,
        captureIdImage: () async => 'synthetic-front.jpg',
        scanIdImage: (_) async => {
          'success': false,
          'code': 'ID_CARD_NOT_DETECTED',
          'message': 'Full card not detected.',
          'extracted': null,
        },
      ),
    );

    await tester.tap(find.text('Scan ID'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Open camera'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Use photo'));
    await tester.pumpAndSettle();
    expect(find.text('Full card not detected.'), findsOneWidget);

    await _openManual(tester);
    expect(find.text('Full name'), findsOneWidget);
    expect(_submitBtn, findsOneWidget);
    await auth.close();
  });

  testWidgets('retake clears extracted identity before opening the camera', (
    tester,
  ) async {
    final auth = AuthCubit(ApiClient(client: ScriptedClient()));
    await pump(
      tester,
      _host(
        auth,
        captureIdImage: () async => 'synthetic-front.jpg',
        scanIdImage: (_) async => {
          'success': true,
          'extracted': {
            'full_name': 'OCR Citizen',
            'national_id': '29001010123456',
            'registered_address_text': 'OCR Address, Cairo',
          },
          'warnings': <String>[],
        },
      ),
    );

    await tester.tap(find.text('Scan ID'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Open camera'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Use photo'));
    await tester.pumpAndSettle();
    expect(find.text('OCR Citizen'), findsOneWidget);

    await tester.tap(find.text('Retake'));
    await tester.pumpAndSettle();
    expect(find.text('OCR Citizen'), findsNothing);
    expect(find.text('Scan the front of your National ID'), findsOneWidget);
    await auth.close();
  });

  testWidgets('successful scan deletes its transient camera file', (
    tester,
  ) async {
    String? discardedPath;
    final auth = AuthCubit(ApiClient(client: ScriptedClient()));
    await pump(
      tester,
      _host(
        auth,
        captureIdImage: () async => 'synthetic-front.jpg',
        discardIdImage: (path) async => discardedPath = path,
        scanIdImage: (_) async => {
          'success': true,
          'extracted': {
            'full_name': 'OCR Citizen',
            'national_id': '29001010123456',
            'registered_address_text': 'OCR Address, Cairo',
          },
          'warnings': <String>[],
        },
      ),
    );

    await tester.tap(find.text('Scan ID'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Open camera'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Use photo'));
    await tester.pumpAndSettle();

    expect(discardedPath, 'synthetic-front.jpg');
    await auth.close();
  });

  testWidgets('Arabic scan-first copy renders without layout exceptions', (
    tester,
  ) async {
    final auth = AuthCubit(ApiClient(client: ScriptedClient()));
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(_host(auth, locale: const Locale('ar')));
    await tester.pump();

    expect(find.text('مسح بطاقة الرقم القومي'), findsOneWidget);
    expect(find.text('إدخال البيانات يدويًا'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await auth.close();
  });
}
