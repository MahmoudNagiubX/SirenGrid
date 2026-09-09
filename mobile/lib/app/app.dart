import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import '../core/api_client.dart';
import '../core/location.dart';
import '../design/components/sg_buttons.dart';
import '../design/sg_icon.dart';
import '../design/theme.dart';
import '../design/tokens.dart';
import '../features/auth/auth_cubit.dart';
import '../features/auth/login_screen.dart';
import '../features/emergency/home_cubit.dart';
import '../features/emergency/location_cubit.dart';
import '../features/tracking/tracking_cubit.dart';
import '../l10n/strings.dart';
import '../notifications/notification_coordinator.dart';
import 'shell.dart';

class SirenGridApp extends StatefulWidget {
  const SirenGridApp({
    super.key,
    required this.api,
    required this.coordinator,
    required this.location,
  });

  final ApiClient api;
  final NotificationCoordinator coordinator;
  final LocationService location;

  @override
  State<SirenGridApp> createState() => _SirenGridAppState();
}

class _SirenGridAppState extends State<SirenGridApp> {
  late final AuthCubit _auth;

  @override
  void initState() {
    super.initState();
    _auth = AuthCubit(
      widget.api,
      onAuthenticated: (_) => widget.coordinator.onAuthenticated(),
      onBeforeLogout: () => widget.coordinator.onLoggedOut(),
    )..restoreSession();
  }

  @override
  void dispose() {
    _auth.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MultiBlocProvider(
      providers: [
        BlocProvider.value(value: _auth),
        BlocProvider.value(value: widget.coordinator),
        BlocProvider(create: (_) => LocationCubit(widget.location)..refresh()),
        BlocProvider(create: (_) => HomeCubit(widget.api, widget.location)),
        BlocProvider(create: (_) => TrackingCubit(widget.api)),
      ],
      child: MaterialApp(
        title: 'SirenGrid Citizen',
        debugShowCheckedModeBanner: false,
        theme: sgTheme(),
        locale: const Locale('en'),
        supportedLocales: SgStrings.supportedLocales,
        localizationsDelegates: const [
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        builder: (context, child) => MediaQuery.withClampedTextScaling(
          maxScaleFactor: 1.6,
          child: child ?? const SizedBox.shrink(),
        ),
        home: const _AuthGate(),
      ),
    );
  }
}

class _AuthGate extends StatelessWidget {
  const _AuthGate();

  @override
  Widget build(BuildContext context) {
    SystemChrome.setSystemUIOverlayStyle(SystemUiOverlayStyle.dark);
    return BlocBuilder<AuthCubit, AuthState>(
      builder: (context, state) {
        return switch (state) {
          Authenticated() => const MainShell(),
          AuthInitial() || AuthRestoring() => const _Splash(),
          AuthFailure(sessionCheckFailure: true, :final message) =>
            _SessionError(message: message),
          _ => const LoginScreen(),
        };
      },
    );
  }
}

class _Splash extends StatelessWidget {
  const _Splash();
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      key: const Key('splash_screen'),
      backgroundColor: SgColors.bgApp,
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const SgIcon('siren', size: 44, color: SgColors.emergency),
            const SizedBox(height: 18),
            const SizedBox(
              width: 22,
              height: 22,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                color: SgColors.emergency,
              ),
            ),
            const SizedBox(height: 14),
            Text(
              context.tr('session.checking'),
              style: SgType.caption.copyWith(color: SgColors.textMuted),
            ),
          ],
        ),
      ),
    );
  }
}

class _SessionError extends StatelessWidget {
  const _SessionError({required this.message});
  final String message;
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      key: const Key('session_error_screen'),
      backgroundColor: SgColors.bgApp,
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const SgIcon(
                  'wifi-off',
                  size: 44,
                  color: SgColors.emergencyHover,
                ),
                const SizedBox(height: 16),
                Text(
                  message.contains('.') && !message.contains(' ')
                      ? context.tr('session.error')
                      : message,
                  textAlign: TextAlign.center,
                  style: SgType.bodyMedium.copyWith(
                    color: SgColors.textPrimary,
                  ),
                ),
                const SizedBox(height: 24),
                SgPrimaryButton(
                  label: context.tr('session.retry'),
                  icon: 'refresh-cw',
                  onPressed: () => context.read<AuthCubit>().restoreSession(),
                ),
                const SizedBox(height: 12),
                SgSecondaryButton(
                  label: context.tr('session.signout'),
                  onPressed: () => context.read<AuthCubit>().logout(),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
