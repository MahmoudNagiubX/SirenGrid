import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import '../core/api_client.dart';
import '../core/localization/locale_cubit.dart';
import '../core/localization/siren_localizations.dart';
import '../core/theme.dart';
import '../core/theme_cubit.dart';
import '../features/auth/auth_cubit.dart';
import '../features/auth/login_screen.dart';
import '../features/emergency_home/home_cubit.dart';
import '../features/tracking/tracking_cubit.dart';
import 'shell.dart';

/// SirenGrid Root Citizen Mobile Application
/// Configures theme, dynamic locale, supported languages, localization delegates,
/// and top-level session routing.
class SirenGridCitizenApp extends StatelessWidget {
  final ApiClient apiClient;

  const SirenGridCitizenApp({super.key, required this.apiClient});

  @override
  Widget build(BuildContext context) {
    return MultiBlocProvider(
      providers: [
        BlocProvider(create: (_) => ThemeCubit()),
        BlocProvider(create: (_) => LocaleCubit()),
        BlocProvider(create: (_) => AuthCubit(apiClient)..checkSession()),
        BlocProvider(create: (_) => HomeCubit(apiClient)),
        BlocProvider(create: (_) => TrackingCubit(apiClient)),
      ],
      child: BlocBuilder<ThemeCubit, ThemeMode>(
        builder: (context, themeMode) {
          return BlocBuilder<LocaleCubit, Locale>(
            builder: (context, locale) {
              return MaterialApp(
                title: 'SirenGrid Citizen',
                theme: AppTheme.themeForLocale(locale, isDark: false),
                darkTheme: AppTheme.themeForLocale(locale, isDark: true),
                themeMode: themeMode,
                locale: locale,
                supportedLocales: const [
                  Locale('ar'),
                  Locale('en'),
                ],
                localizationsDelegates: const [
                  SirenLocalizations.delegate,
                  GlobalMaterialLocalizations.delegate,
                  GlobalWidgetsLocalizations.delegate,
                  GlobalCupertinoLocalizations.delegate,
                ],
                debugShowCheckedModeBanner: false,
                home: BlocBuilder<AuthCubit, AuthState>(
                  builder: (context, state) {
                    if (state is Authenticated || state is AuthPreview) {
                      return const MainShell();
                    }
                    if (state is AuthCheckingSession || state is AuthInitial) {
                      return Scaffold(
                        key: const Key('app_splash_screen'),
                        backgroundColor: context.colors.background,
                        body: const Center(
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(Icons.emergency, size: 48, color: AppColors.primary),
                              SizedBox(height: 16),
                              CircularProgressIndicator(strokeWidth: 2, color: AppColors.primary),
                            ],
                          ),
                        ),
                      );
                    }
                    if (state is AuthFailure && state.isSessionCheckFailure) {
                      // Truthful representation of temporary connectivity failure during session check
                      return Scaffold(
                        key: const Key('app_session_error_screen'),
                        backgroundColor: context.colors.background,
                        body: SafeArea(
                          child: Padding(
                            padding: const EdgeInsets.all(24.0),
                            child: Center(
                              child: Column(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  const Icon(Icons.cloud_off, size: 48, color: AppColors.emergencyStrong),
                                  const SizedBox(height: 16),
                                  Text(
                                    state.message,
                                    textAlign: TextAlign.center,
                                    style: TextStyle(
                                      fontSize: 16,
                                      fontWeight: FontWeight.w600,
                                      color: context.colors.textPrimary,
                                    ),
                                  ),
                                  const SizedBox(height: 24),
                                  ElevatedButton.icon(
                                    onPressed: () => context.read<AuthCubit>().checkSession(),
                                    icon: const Icon(Icons.refresh),
                                    label: const Text('Retry Connection'),
                                  ),
                                  const SizedBox(height: 12),
                                  TextButton(
                                    onPressed: () => context.read<AuthCubit>().logout(),
                                    child: const Text('Sign Out / Clear Session'),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ),
                      );
                    }
                    return const LoginScreen();
                  },
                ),
              );
            },
          );
        },
      ),
    );
  }
}
