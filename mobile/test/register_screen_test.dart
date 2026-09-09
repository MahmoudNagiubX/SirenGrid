import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
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

Widget _host(AuthCubit auth, {LocationService? location}) => MaterialApp(
  theme: sgTheme(),
  supportedLocales: SgStrings.supportedLocales,
  home: BlocProvider<AuthCubit>.value(
    value: auth,
    child: RegisterScreen(locationService: location),
  ),
);

Future<void> _fillValid(WidgetTester tester) async {
  await tester.enterText(find.byType(TextField).at(0), 'New Citizen');
  await tester.enterText(find.byType(TextField).at(1), '01111222333');
  await tester.enterText(find.byType(TextField).at(2), '29001010123456');
  await tester.enterText(find.byType(TextField).at(3), '4321');
  await tester.enterText(find.byType(TextField).at(4), '4321');
  await tester.enterText(
    find.byType(TextField).at(5),
    '8 Test Street, Nasr City, Cairo',
  );
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

  testWidgets('renders every registration field + submit', (tester) async {
    final auth = AuthCubit(ApiClient(client: ScriptedClient()));
    await pump(tester, _host(auth));

    expect(find.byKey(const Key('register_screen')), findsOneWidget);
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

    await tester.tap(_submitBtn);
    await tester.pump();

    expect(find.text('Enter your full name.'), findsOneWidget);
    expect(find.text('National ID must be 14 digits.'), findsOneWidget);
    expect(client.requests, isEmpty);
    await auth.close();
  });

  testWidgets('PIN mismatch is caught client-side', (tester) async {
    final client = ScriptedClient();
    final auth = AuthCubit(ApiClient(client: client));
    await pump(tester, _host(auth));

    await _fillValid(tester);
    await tester.enterText(find.byType(TextField).at(4), '9999');
    await tester.tap(_submitBtn);
    await tester.pump();

    expect(find.text("PINs don't match."), findsOneWidget);
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
}
