import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import '../../core/location.dart';
import '../../design/components/sg_buttons.dart';
import '../../design/components/sg_cards.dart';
import '../../design/components/sg_feedback.dart';
import '../../design/sg_icon.dart';
import '../../design/tokens.dart';
import '../../l10n/strings.dart';
import '../auth/auth_cubit.dart';
import 'confirmation_sheet.dart';
import 'emergency_service.dart';
import 'home_cubit.dart';
import 'location_cubit.dart';

/// Screen 1 — Emergency Home (brief §15). Controlled red hero over light
/// surfaces; 2×2 service choice; one persistent emergency CTA above the nav.
class HomeScreen extends StatefulWidget {
  const HomeScreen({
    super.key,
    required this.onOpenAccount,
    required this.onSubmitted,
    this.showClearTheWay = false,
    this.onDismissClearTheWay,
  });

  final VoidCallback onOpenAccount;
  final void Function(HomeSubmitted result) onSubmitted;
  final bool showClearTheWay;
  final VoidCallback? onDismissClearTheWay;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  EmergencyService _selected = EmergencyService.ambulance;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<LocationCubit>().refresh();
    });
  }

  Future<void> _request(EmergencyService service) async {
    final result = await showConfirmationSheet(context, service: service);
    if (result != null && mounted) widget.onSubmitted(result);
  }

  @override
  Widget build(BuildContext context) {
    final profile = context.watch<AuthCubit>().state.profile;
    final firstName = (profile?.displayName ?? '').split(' ').first;

    return Scaffold(
      key: const Key('home_screen'),
      backgroundColor: SgColors.bgApp,
      body: Column(
        children: [
          _Hero(
            greeting: firstName.isEmpty
                ? context.tr('home.greeting')
                : '${context.tr('home.greeting')}, $firstName',
            headline: context.tr('home.headline'),
            initials: profile?.initials ?? 'SG',
            onOpenAccount: widget.onOpenAccount,
          ),
          Expanded(
            child: Stack(
              children: [
                SingleChildScrollView(
                  padding: const EdgeInsets.fromLTRB(
                    SgSpace.page,
                    20,
                    SgSpace.page,
                    190,
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      if (widget.showClearTheWay) ...[
                        SgAlertBanner(
                          message: context.tr('home.clear_the_way'),
                          icon: 'siren',
                          onDismiss: widget.onDismissClearTheWay,
                        ),
                        const SizedBox(height: 16),
                      ],
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Flexible(
                            child: Text(
                              context.tr('home.question'),
                              style: SgType.cardHeading.copyWith(
                                color: SgColors.heading,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                          ),
                          const SizedBox(width: 8),
                          SgStatusChip(
                            context.tr('home.step1'),
                            tone: SgChipTone.neutral,
                            dot: false,
                          ),
                        ],
                      ),
                      const SizedBox(height: 14),
                      GridView.count(
                        crossAxisCount: 2,
                        shrinkWrap: true,
                        physics: const NeverScrollableScrollPhysics(),
                        mainAxisSpacing: 12,
                        crossAxisSpacing: 12,
                        childAspectRatio: 1.35,
                        children: [
                          for (final s in EmergencyService.values)
                            SgServiceCard(
                              key: Key('service_card_${s.name}'),
                              icon: s.icon,
                              label: context.tr(s.labelKey),
                              selected: _selected == s,
                              onTap: () => setState(() => _selected = s),
                            ),
                        ],
                      ),
                      const SizedBox(height: 18),
                      _LocationStrip(
                        onRequestPermission: () {
                          context.read<LocationCubit>().requestPermission();
                        },
                        onOpenSettings: () {
                          context.read<LocationCubit>().openLocationSettings();
                        },
                      ),
                    ],
                  ),
                ),
                Positioned(
                  left: 0,
                  right: 0,
                  bottom: 0,
                  child: IgnorePointer(
                    ignoring: true,
                    child: Container(
                      height: 120,
                      decoration: const BoxDecoration(
                        gradient: LinearGradient(
                          begin: Alignment.topCenter,
                          end: Alignment.bottomCenter,
                          colors: [Color(0x00EDF2F4), SgColors.bgApp],
                          stops: [0, 0.46],
                        ),
                      ),
                    ),
                  ),
                ),
                Positioned(
                  left: SgSpace.page,
                  right: SgSpace.page,
                  bottom: 14,
                  child: BlocBuilder<HomeCubit, HomeState>(
                    builder: (context, state) => SgEmergencyButton(
                      label:
                          '${context.tr('home.request')} ${context.tr(_selected.labelKey)}',
                      icon: _selected.icon,
                      full: true,
                      pulsing: state is HomeIdle,
                      loading: state is HomeSubmitting,
                      onPressed: state is HomeSubmitting
                          ? null
                          : () => _request(_selected),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _Hero extends StatelessWidget {
  const _Hero({
    required this.greeting,
    required this.headline,
    required this.initials,
    required this.onOpenAccount,
  });

  final String greeting;
  final String headline;
  final String initials;
  final VoidCallback onOpenAccount;

  @override
  Widget build(BuildContext context) {
    final topPad = MediaQuery.of(context).padding.top;
    return Container(
      decoration: const BoxDecoration(
        gradient: SgColors.gradientHero,
        borderRadius: BorderRadius.vertical(bottom: Radius.circular(30)),
      ),
      child: Stack(
        children: [
          Positioned(
            right: -70,
            top: -60,
            child: Container(
              width: 240,
              height: 240,
              decoration: const BoxDecoration(
                shape: BoxShape.circle,
                gradient: RadialGradient(
                  colors: [Color(0x29FFFFFF), Color(0x00FFFFFF)],
                  stops: [0, 0.7],
                ),
              ),
            ),
          ),
          Padding(
            padding: EdgeInsets.fromLTRB(
              SgSpace.page,
              topPad + 14,
              SgSpace.page,
              22,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.center,
                      children: [
                        Text(
                          context.tr('app.name'),
                          style: const TextStyle(
                            fontSize: 15,
                            fontWeight: FontWeight.w700,
                            color: Colors.white,
                            letterSpacing: -0.15,
                          ),
                        ),
                        const SizedBox(width: 3),
                        Container(
                          width: 5,
                          height: 5,
                          decoration: const BoxDecoration(
                            color: Colors.white70,
                            shape: BoxShape.circle,
                          ),
                        ),
                      ],
                    ),
                    Semantics(
                      button: true,
                      label: context.tr('nav.account'),
                      child: GestureDetector(
                        onTap: onOpenAccount,
                        child: Container(
                          width: 40,
                          height: 40,
                          alignment: Alignment.center,
                          decoration: BoxDecoration(
                            color: Colors.white.withValues(alpha: 0.16),
                            shape: BoxShape.circle,
                            border: Border.all(
                              color: Colors.white.withValues(alpha: 0.4),
                              width: 1.5,
                            ),
                          ),
                          child: Text(
                            initials,
                            style: const TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.w700,
                              fontSize: 13,
                            ),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 24),
                Text(
                  greeting,
                  style: SgType.caption.copyWith(
                    color: Colors.white,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 6),
                ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 260),
                  child: Text(
                    headline,
                    style: const TextStyle(
                      fontSize: 30,
                      height: 36 / 30,
                      fontWeight: FontWeight.w700,
                      color: Colors.white,
                      letterSpacing: -0.6,
                    ),
                  ),
                ),
                const SizedBox(height: 20),
                _HeroLocation(),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _HeroLocation extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return BlocBuilder<LocationCubit, LocationReadiness>(
      builder: (context, r) {
        final ready = r == LocationReadiness.ready;
        final title = switch (r) {
          LocationReadiness.ready => context.tr('home.location_ready'),
          LocationReadiness.servicesOff => context.tr('home.location_off'),
          LocationReadiness.permissionBlocked => context.tr(
            'home.location_blocked',
          ),
          LocationReadiness.permissionRequired => context.tr(
            'home.location_permission',
          ),
          LocationReadiness.unknown => context.tr('home.location_finding'),
        };
        return Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: 0.14),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: Colors.white.withValues(alpha: 0.28)),
          ),
          child: Row(
            children: [
              const SgIcon(
                'map-pin',
                size: 18,
                color: Colors.white,
                strokeWidth: 2.2,
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title.toUpperCase(),
                      style: SgType.chip.copyWith(
                        color: Colors.white,
                        letterSpacing: 0.4,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      ready
                          ? context.tr('home.location_ready')
                          : context.tr('home.location_finding'),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w500,
                        color: Colors.white,
                      ),
                    ),
                  ],
                ),
              ),
              Container(
                width: 8,
                height: 8,
                decoration: BoxDecoration(
                  color: ready ? Colors.white : Colors.white54,
                  shape: BoxShape.circle,
                  boxShadow: ready
                      ? [
                          BoxShadow(
                            color: Colors.white.withValues(alpha: 0.25),
                            blurRadius: 0,
                            spreadRadius: 4,
                          ),
                        ]
                      : null,
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _LocationStrip extends StatelessWidget {
  const _LocationStrip({
    required this.onRequestPermission,
    required this.onOpenSettings,
  });
  final VoidCallback onRequestPermission;
  final VoidCallback onOpenSettings;

  @override
  Widget build(BuildContext context) {
    return BlocBuilder<LocationCubit, LocationReadiness>(
      builder: (context, r) {
        if (r == LocationReadiness.ready) {
          return SgLocationCard(
            title: context.tr('home.location_ready'),
            state: SgLocationCardState.ready,
          );
        }
        final (state, action, cb) = switch (r) {
          LocationReadiness.servicesOff => (
            SgLocationCardState.servicesOff,
            context.tr('home.location_settings'),
            onOpenSettings,
          ),
          LocationReadiness.permissionBlocked => (
            SgLocationCardState.blocked,
            context.tr('home.location_settings'),
            onOpenSettings,
          ),
          LocationReadiness.permissionRequired => (
            SgLocationCardState.permissionRequired,
            context.tr('home.location_retry'),
            onRequestPermission,
          ),
          _ => (
            SgLocationCardState.locating,
            context.tr('home.location_retry'),
            onRequestPermission,
          ),
        };
        final title = switch (r) {
          LocationReadiness.servicesOff => context.tr('home.location_off'),
          LocationReadiness.permissionBlocked => context.tr(
            'home.location_blocked',
          ),
          LocationReadiness.permissionRequired => context.tr(
            'home.location_permission',
          ),
          _ => context.tr('home.location_finding'),
        };
        return SgLocationCard(
          title: title,
          state: state,
          actionLabel: action,
          onAction: cb,
        );
      },
    );
  }
}
