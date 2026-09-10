import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import '../../design/components/sg_buttons.dart';
import '../../design/components/sg_cards.dart';
import '../../design/components/sg_feedback.dart';
import '../../design/sg_icon.dart';
import '../../design/tokens.dart';
import '../../l10n/strings.dart';
import '../emergency/emergency_service.dart';
import 'tracking_cubit.dart';
import 'tracking_map.dart';
import 'tracking_models.dart';

/// Screen 2 — Live Response Tracking (brief §4/§13/§14). The app's hero screen:
/// dominant real map, distinct citizen pin vs service-typed responder marker,
/// approved route, floating status header, docked responder card with a compact
/// step timeline. Every number is backend-owned; simulated data is labelled
/// truthfully; terminal states stop implying live movement.
class TrackingScreen extends StatefulWidget {
  const TrackingScreen({super.key, required this.onGoHome});
  final VoidCallback onGoHome;

  @override
  State<TrackingScreen> createState() => _TrackingScreenState();
}

class _TrackingScreenState extends State<TrackingScreen>
    with WidgetsBindingObserver {
  final _mapKey = GlobalKey<TrackingMapState>();

  // Captured in didChangeDependencies, not read at dispose time: if this
  // screen is torn down as part of an ancestor unmounting (e.g. the shell
  // swapping away on logout), this widget's own BuildContext is already
  // deactivated by the time dispose() runs, and context.read() on a
  // deactivated context throws. The cubit instance itself is still valid to
  // call into during dispose; only the context lookup is unsafe.
  late TrackingCubit _cubit;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<TrackingCubit>().start();
    });
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _cubit = context.read<TrackingCubit>();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _cubit.pause();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _cubit.refreshNow();
    } else if (state == AppLifecycleState.paused) {
      _cubit.pause();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      key: const Key('tracking_screen'),
      backgroundColor: SgColors.mapBg,
      body: BlocBuilder<TrackingCubit, TrackingState>(
        builder: (context, state) {
          return switch (state) {
            TrackingIdle() => _NoActiveRequest(onGoHome: widget.onGoHome),
            TrackingLoading() => const Center(
              child: CircularProgressIndicator(color: SgColors.mapRoute),
            ),
            TrackingUnavailable(:final message, :final recoverable) =>
              _Unavailable(
                message: message,
                onRetry: recoverable
                    ? () => context.read<TrackingCubit>().start()
                    : null,
                onGoHome: widget.onGoHome,
              ),
            TrackingReady(:final snapshot, :final stalePolls) => _TrackingBody(
              mapKey: _mapKey,
              snapshot: snapshot,
              degraded: stalePolls > 0,
              onGoHome: widget.onGoHome,
              onRetry: () => context.read<TrackingCubit>().refreshNow(),
            ),
          };
        },
      ),
    );
  }
}

class _TrackingBody extends StatelessWidget {
  const _TrackingBody({
    required this.mapKey,
    required this.snapshot,
    required this.degraded,
    required this.onGoHome,
    required this.onRetry,
  });

  final GlobalKey<TrackingMapState> mapKey;
  final TrackingSnapshot snapshot;
  final bool degraded;
  final VoidCallback onGoHome;
  final VoidCallback onRetry;

  EmergencyService get _service =>
      EmergencyService.fromApiCode(snapshot.serviceCode);

  @override
  Widget build(BuildContext context) {
    final s = snapshot;
    final showMap =
        s.emergencyLocation != null ||
        (s.responder?.location != null) ||
        (s.route?.polyline.isNotEmpty ?? false);
    final topPad = MediaQuery.of(context).padding.top;

    return Stack(
      children: [
        Positioned.fill(
          child: showMap
              ? TrackingMap(
                  key: mapKey,
                  snapshot: s,
                  serviceIcon: _service.icon,
                )
              : TrackingMapPlaceholder(
                  caption: context.tr('track.map_preparing'),
                ),
        ),
        // legibility gradient under the header
        Positioned(
          top: 0,
          left: 0,
          right: 0,
          height: 210,
          child: IgnorePointer(
            child: Container(
              decoration: const BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [Color(0xF0E3EAF6), Color(0x00E3EAF6)],
                ),
              ),
            ),
          ),
        ),
        // floating header
        Positioned(
          top: topPad + 8,
          left: 18,
          right: 18,
          child: _Header(
            title: _headline(context),
            statusLabel: context.tr('status.${s.rawStatus}'),
            requestRef: _shortRef(s.requestId),
            terminal: s.status.isTerminal,
            onBack: onGoHome,
          ),
        ),
        // recenter
        if (showMap)
          Positioned(
            right: 18,
            bottom: 320,
            child: _RoundIconButton(
              icon: 'navigation',
              onTap: () => mapKey.currentState?.recenter(),
              tooltip: context.tr('track.recenter'),
            ),
          ),
        // docked responder / state card
        Positioned(
          left: 0,
          right: 0,
          bottom: 0,
          child: _DockedCard(
            snapshot: s,
            service: _service,
            degraded: degraded,
            onRetry: onRetry,
          ),
        ),
      ],
    );
  }

  String _headline(BuildContext context) {
    final svc = context.tr(_service.labelKey);
    return switch (snapshot.status) {
      CitizenRequestStatus.received ||
      CitizenRequestStatus.underReview => context.tr('track.received'),
      CitizenRequestStatus.responseAssigned => context.tr('track.assigned'),
      CitizenRequestStatus.enRoute => '$svc ${context.tr('track.on_the_way')}',
      CitizenRequestStatus.arrived => context.tr('track.arrived'),
      CitizenRequestStatus.completed => context.tr('track.completed'),
      CitizenRequestStatus.cancelled => context.tr('track.cancelled'),
      CitizenRequestStatus.unknown => context.tr('track.title'),
    };
  }

  static String _shortRef(String id) {
    final compact = id.replaceAll('-', '');
    return 'SG-${compact.substring(0, compact.length.clamp(0, 6)).toUpperCase()}';
  }
}

class _Header extends StatelessWidget {
  const _Header({
    required this.title,
    required this.statusLabel,
    required this.requestRef,
    required this.terminal,
    required this.onBack,
  });

  final String title;
  final String statusLabel;
  final String requestRef;
  final bool terminal;
  final VoidCallback onBack;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _RoundIconButton(icon: 'arrow-left', onTap: onBack, square: true),
        const SizedBox(width: 10),
        Expanded(
          child: Container(
            padding: const EdgeInsets.fromLTRB(16, 13, 16, 14),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(18),
              boxShadow: SgShadows.card,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  title,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: SgType.cardHeading.copyWith(
                    color: SgColors.heading,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 9),
                Row(
                  children: [
                    SgStatusChip(
                      statusLabel,
                      tone: terminal ? SgChipTone.neutral : SgChipTone.urgent,
                      pulsing: !terminal,
                    ),
                    const SizedBox(width: 9),
                    Flexible(
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          const SgIcon(
                            'route',
                            size: 13,
                            color: SgColors.infoStrong,
                          ),
                          const SizedBox(width: 5),
                          Flexible(
                            child: Text(
                              requestRef,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: SgType.caption.copyWith(
                                color: SgColors.textMuted,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _DockedCard extends StatelessWidget {
  const _DockedCard({
    required this.snapshot,
    required this.service,
    required this.degraded,
    required this.onRetry,
  });

  final TrackingSnapshot snapshot;
  final EmergencyService service;
  final bool degraded;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final s = snapshot;
    final steps = [
      context.tr('track.step_received'),
      context.tr('track.step_assigned'),
      context.tr('track.step_en_route'),
      context.tr('track.step_arrived'),
    ];

    // No responder yet — calm empty state inside the sheet shell.
    if (s.responder == null) {
      return _SheetShell(
        child: SgEmptyState(
          icon: 'clock',
          title: context.tr('track.no_responder'),
          description: context.tr('track.no_responder_body'),
          action: degraded
              ? SgSecondaryButton(
                  label: context.tr('track.retry'),
                  onPressed: onRetry,
                )
              : null,
        ),
      );
    }

    final responder = s.responder!;
    final eta = s.etaMinutes;
    final etaText = eta == null
        ? null
        : (context.tr('track.eta_prefix') == 'ETA'
              ? '$eta min'
              : '$eta ${SgStrings.of(context).isArabic ? 'د' : 'min'}');
    final freshness = _freshnessLine(context, s);
    final provenance = _provenanceLabel(context, s);

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (s.effectiveEtaSeconds == null && !s.status.isTerminal)
          Padding(
            padding: const EdgeInsets.fromLTRB(18, 0, 18, 8),
            child: SgInfoCard(
              icon: 'clock',
              title: context.tr('track.eta_preparing'),
              tone: SgChipTone.info,
            ),
          ),
        if (!s.hasResponderLocation && !s.status.isTerminal)
          Padding(
            padding: const EdgeInsets.fromLTRB(18, 0, 18, 8),
            child: SgInfoCard(
              icon: 'map-pin',
              title: context.tr('track.responder_location_missing'),
              tone: SgChipTone.neutral,
            ),
          ),
        SgResponderCard(
          label: _unitLabel(context, responder, service),
          icon: service.icon,
          statusLabel: context.tr('status.${s.rawStatus}'),
          steps: steps,
          activeStep: s.status.timelineStep,
          eta: etaText,
          freshnessLabel: freshness,
          stale: s.isStale || degraded,
          provenanceLabel: provenance,
        ),
      ],
    );
  }

  static String _unitLabel(
    BuildContext context,
    ResponderView r,
    EmergencyService s,
  ) {
    if (r.label.isNotEmpty) return r.label;
    return context.tr(s.labelKey);
  }

  static String? _freshnessLine(BuildContext context, TrackingSnapshot s) {
    final last = s.responder?.lastUpdated ?? s.lastUpdated;
    if (last == null) return null;
    final secs = DateTime.now().difference(last).inSeconds;
    if (secs < 0) return null;
    final str = SgStrings.of(context);
    if (secs < 90) {
      return str.t('track.updated_ago').replaceFirst('{n}', '$secs');
    }
    final mins = (secs / 60).round();
    return str.t('track.updated_min_ago').replaceFirst('{n}', '$mins');
  }

  static String? _provenanceLabel(BuildContext context, TrackingSnapshot s) {
    if (s.status.isTerminal) return null;
    if (!s.isSimulated) return null;
    // Truthful demo wording — never "Live GPS" for simulated data.
    if (s.route?.isSimulatedProjection ?? false) {
      return context.tr('track.demo_route');
    }
    return context.tr('track.demo_position');
  }
}

class _SheetShell extends StatelessWidget {
  const _SheetShell({required this.child});
  final Widget child;
  @override
  Widget build(BuildContext context) => Container(
    width: double.infinity,
    decoration: const BoxDecoration(
      color: SgColors.bgSurface,
      borderRadius: BorderRadius.vertical(top: Radius.circular(SgRadius.sheet)),
      boxShadow: SgShadows.sheet,
    ),
    child: SafeArea(top: false, child: child),
  );
}

class _NoActiveRequest extends StatelessWidget {
  const _NoActiveRequest({required this.onGoHome});
  final VoidCallback onGoHome;
  @override
  Widget build(BuildContext context) {
    return Container(
      color: SgColors.bgApp,
      child: SafeArea(
        child: Center(
          child: SgEmptyState(
            icon: 'map',
            title: context.tr('track.no_active'),
            description: context.tr('track.no_active_body'),
            action: SgPrimaryButton(
              label: context.tr('track.go_home'),
              icon: 'house',
              onPressed: onGoHome,
            ),
          ),
        ),
      ),
    );
  }
}

class _Unavailable extends StatelessWidget {
  const _Unavailable({
    required this.message,
    required this.onGoHome,
    this.onRetry,
  });
  final String message;
  final VoidCallback onGoHome;
  final VoidCallback? onRetry;
  @override
  Widget build(BuildContext context) {
    return Container(
      color: SgColors.bgApp,
      child: SafeArea(
        child: Center(
          child: SgEmptyState(
            icon: 'wifi-off',
            title: message,
            action: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (onRetry != null)
                  SgPrimaryButton(
                    label: context.tr('common.retry'),
                    icon: 'refresh-cw',
                    onPressed: onRetry,
                  ),
                if (onRetry != null) const SizedBox(width: 10),
                SgSecondaryButton(
                  label: context.tr('track.go_home'),
                  onPressed: onGoHome,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _RoundIconButton extends StatelessWidget {
  const _RoundIconButton({
    required this.icon,
    required this.onTap,
    this.square = false,
    this.tooltip,
  });
  final String icon;
  final VoidCallback onTap;
  final bool square;
  final String? tooltip;

  @override
  Widget build(BuildContext context) {
    final child = GestureDetector(
      onTap: onTap,
      child: Container(
        width: 44,
        height: 44,
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(square ? 16 : 999),
          boxShadow: SgShadows.card,
        ),
        child: Center(
          child: SgIcon(
            icon,
            size: 19,
            color: SgColors.heading,
            strokeWidth: 2.2,
          ),
        ),
      ),
    );
    return tooltip == null ? child : Tooltip(message: tooltip!, child: child);
  }
}
