import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import '../core/storage.dart';
import '../design/components/sg_nav.dart';
import '../design/tokens.dart';
import '../features/account/account_screen.dart';
import '../features/emergency/home_cubit.dart';
import '../features/emergency/home_screen.dart';
import '../features/tracking/tracking_cubit.dart';
import '../features/tracking/tracking_screen.dart';
import '../l10n/strings.dart';
import '../notifications/notification_coordinator.dart';

/// Authenticated container — exactly three destinations (brief §17). Owns the
/// active-request flag and the confirm → submit → track hand-off, and routes
/// notification intents (refetch + navigate; Clear-the-Way banner on Home).
class MainShell extends StatefulWidget {
  const MainShell({super.key});

  @override
  State<MainShell> createState() => _MainShellState();
}

class _MainShellState extends State<MainShell> {
  int _index = 0;
  bool _hasActiveRequest = false;
  bool _showClearTheWay = false;
  StreamSubscription<NotificationIntent>? _intentSub;

  @override
  void initState() {
    super.initState();
    _loadActiveRequest();
    _intentSub = context.read<NotificationCoordinator>().intents.listen(
      _onIntent,
    );
  }

  @override
  void dispose() {
    _intentSub?.cancel();
    super.dispose();
  }

  Future<void> _loadActiveRequest() async {
    final id = await SecureStore.readActiveRequestId();
    if (mounted && id != null && id.isNotEmpty) {
      setState(() => _hasActiveRequest = true);
    }
  }

  void _onIntent(NotificationIntent intent) {
    if (!mounted) return;
    if (intent.isClearTheWay) {
      setState(() => _showClearTheWay = true);
      return;
    }
    // Any request-scoped push: refetch canonical state, and (on tap) surface
    // the Track tab. Push content itself is never treated as truth.
    context.read<TrackingCubit>().refreshNow();
    if (intent.isRequestScoped) {
      setState(() => _hasActiveRequest = true);
      if (intent.fromTap) {
        _goTo(1);
      } else if (intent.title != null) {
        // Foreground: present in-app rather than relying on the OS tray.
        ScaffoldMessenger.of(context)
          ..hideCurrentSnackBar()
          ..showSnackBar(
            SnackBar(
              content: Text(intent.body ?? intent.title!),
              action: SnackBarAction(
                label: context.tr('nav.track'),
                onPressed: () => _goTo(1),
              ),
            ),
          );
      }
    }
  }

  void _goTo(int i) {
    setState(() => _index = i);
    if (i == 1) context.read<TrackingCubit>().start();
  }

  void _onSubmitted(HomeSubmitted result) {
    setState(() {
      _hasActiveRequest = true;
      _index = 1;
    });
    context.read<TrackingCubit>().start(requestId: result.requestId);
  }

  @override
  Widget build(BuildContext context) {
    final pages = [
      HomeScreen(
        onOpenAccount: () => _goTo(2),
        onSubmitted: _onSubmitted,
        showClearTheWay: _showClearTheWay,
        onDismissClearTheWay: () => setState(() => _showClearTheWay = false),
      ),
      TrackingScreen(onGoHome: () => _goTo(0)),
      const AccountScreen(),
    ];

    return PopScope(
      canPop: _index == 0,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _goTo(0);
      },
      child: Scaffold(
        backgroundColor: SgColors.bgApp,
        body: IndexedStack(index: _index, children: pages),
        bottomNavigationBar: Padding(
          padding: EdgeInsets.fromLTRB(
            14,
            0,
            14,
            12 + MediaQuery.of(context).padding.bottom,
          ),
          child: SgBottomNavigation(
            currentIndex: _index,
            activeRequest: _hasActiveRequest,
            onTap: _goTo,
          ),
        ),
      ),
    );
  }
}
