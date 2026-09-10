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
            // The hero above already consumes the top status-bar inset for its
            // own padding; without removing it here too, the service grid's
            // GridView (a ScrollView, which safe-pads its main axis by
            // MediaQuery.padding automatically) silently adds that same inset
            // a second time, overflowing the non-scrolling layout below by
            // exactly the status-bar height.
            child: MediaQuery.removePadding(
              context: context,
              removeTop: true,
              child: LayoutBuilder(
                builder: (context, constraints) => _ServiceArea(
                  available: constraints.maxHeight,
                  showClearTheWay: widget.showClearTheWay,
                  onDismissClearTheWay: widget.onDismissClearTheWay,
                  selected: _selected,
                  onSelect: (s) => setState(() => _selected = s),
                  cta: BlocBuilder<HomeCubit, HomeState>(
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
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// The area below the hero: the service question, the 2×2 service grid, an
/// optional location-action card, and the Request CTA — all in one non-scrolling
/// flow. The grid is sized to the height the device actually hands us and any
/// leftover is spread thinly across the four vertical gaps, so the composition
/// stays action-first with no single dead zone. Only extreme text scale / very
/// short viewports (or the Clear-the-Way banner) fall back to a scroll.
class _ServiceArea extends StatelessWidget {
  const _ServiceArea({
    required this.available,
    required this.showClearTheWay,
    required this.onDismissClearTheWay,
    required this.selected,
    required this.onSelect,
    required this.cta,
  });

  final double available;
  final bool showClearTheWay;
  final VoidCallback? onDismissClearTheWay;
  final EmergencyService selected;
  final ValueChanged<EmergencyService> onSelect;
  final Widget cta;

  // Base 8px-grid rhythm (mission §3). On the target device these are the
  // exact gaps; the service cards take a computed height so the whole column
  // just fills the viewport with no scroll and no dead band.
  static const double _heroToTitle = 20;
  static const double _titleToGrid = 16;
  static const double _gridRowGap = 12;
  static const double _gridToCta = 18;
  static const double _ctaToNav = 14;
  static const double _ctaHeight = 60; // SgEmergencyButton pill
  static const double _minCell = 112; // keeps icon + label + touch target
  static const double _maxCell = 140; // dense mobile tile, not a dashboard card

  /// The section heading's real rendered height for [text] at [maxWidth],
  /// honoring the current locale direction and system font scale — the
  /// non-scrolling layout below must reserve the space the heading actually
  /// takes, not an assumed single-line constant.
  ///
  /// Resolves against the ambient [DefaultTextStyle] first (the app theme
  /// applies Google Fonts Rubik there, not on [SgType.cardHeading] itself) so
  /// this measures the same font the real `Text` widget below renders with —
  /// the previously unresolved fallback-font measurement under-counted the
  /// wider/taller Rubik render and made the overflow worse, not better.
  static double _measureHeadingHeight(
    BuildContext context,
    String text,
    double maxWidth,
  ) {
    final effectiveStyle = DefaultTextStyle.of(context).style
        .merge(SgType.cardHeading.copyWith(fontWeight: FontWeight.w700));
    final painter = TextPainter(
      text: TextSpan(text: text, style: effectiveStyle),
      textDirection: Directionality.of(context),
      textScaler: MediaQuery.textScalerOf(context),
    )..layout(maxWidth: maxWidth);
    return painter.height;
  }

  @override
  Widget build(BuildContext context) {
    final readiness = context.watch<LocationCubit>().state;
    final needsLocationAction =
        readiness == LocationReadiness.servicesOff ||
        readiness == LocationReadiness.permissionBlocked ||
        readiness == LocationReadiness.permissionRequired;
    // Rendered height of the location-action card incl. its own top inset.
    final stripReserve = needsLocationAction ? 92.0 : 0.0;

    // `_titleBand` assumes one line; a long translated question or a larger
    // system font scale can wrap it to two, which the fixed constant doesn't
    // account for and silently overflows the non-scrolling layout below. Measure
    // the heading's real height for this context/width instead of assuming it.
    final headingWidth = MediaQuery.sizeOf(context).width - SgSpace.page * 2;
    final headingHeight = _measureHeadingHeight(
      context,
      context.tr('home.question'),
      headingWidth,
    );

    // Everything except the two grid rows.
    final nonGrid =
        _heroToTitle +
        headingHeight +
        _titleToGrid +
        _gridRowGap +
        _gridToCta +
        _ctaHeight +
        _ctaToNav +
        stripReserve;
    final cell = ((available - nonGrid) / 2).clamp(_minCell, _maxCell);
    // Any pixels left once the cards hit their cap are split — a little above
    // the section title, a little below the CTA — so no single gap reads as a
    // dead band and the nav still sits tight (mission §3/§7).
    final slack = (available - nonGrid - 2 * cell).clamp(0.0, 160.0);
    final gapTop = slack * 0.4;
    final gapTail = slack * 0.6;
    // Below ~2 usable rows, fall back to a real scroll so nothing clips.
    final fitsWithoutScroll = !showClearTheWay && (available - nonGrid) >= 224;

    final heading = Text(
      context.tr('home.question'),
      style: SgType.cardHeading.copyWith(
        color: SgColors.heading,
        fontWeight: FontWeight.w700,
      ),
    );

    final grid = _ServiceGrid(
      selected: selected,
      onSelect: onSelect,
      cellExtent: cell,
      rowGap: _gridRowGap,
    );

    final locationStrip = _LocationStrip(
      onRequestPermission: () =>
          context.read<LocationCubit>().requestPermission(),
      onOpenSettings: () =>
          context.read<LocationCubit>().openLocationSettings(),
    );

    if (fitsWithoutScroll) {
      return Padding(
        padding: const EdgeInsets.fromLTRB(
          SgSpace.page,
          0,
          SgSpace.page,
          _ctaToNav,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(height: _heroToTitle + gapTop),
            heading,
            const SizedBox(height: _titleToGrid),
            grid,
            locationStrip,
            const SizedBox(height: _gridToCta),
            cta,
            if (gapTail > 0) SizedBox(height: gapTail),
          ],
        ),
      );
    }

    // Accessibility / very short viewport fallback — a real scroll is allowed
    // here so nothing is ever clipped.
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(SgSpace.page, 16, SgSpace.page, 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (showClearTheWay) ...[
            SgAlertBanner(
              message: context.tr('home.clear_the_way'),
              icon: 'siren',
              onDismiss: onDismissClearTheWay,
            ),
            const SizedBox(height: 16),
          ],
          heading,
          const SizedBox(height: _titleToGrid),
          _ServiceGrid(
            selected: selected,
            onSelect: onSelect,
            cellExtent: 120,
            rowGap: _gridRowGap,
          ),
          locationStrip,
          const SizedBox(height: _gridToCta),
          cta,
        ],
      ),
    );
  }
}

/// The 2×2 service choice. A plain non-scrolling grid with a fixed row height
/// ([cellExtent], computed by [_ServiceArea] from the space the device gives).
class _ServiceGrid extends StatelessWidget {
  const _ServiceGrid({
    required this.selected,
    required this.onSelect,
    required this.cellExtent,
    this.rowGap = 12,
  });

  final EmergencyService selected;
  final ValueChanged<EmergencyService> onSelect;
  final double cellExtent;
  final double rowGap;

  @override
  Widget build(BuildContext context) {
    return GridView(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 2,
        mainAxisSpacing: rowGap,
        crossAxisSpacing: 12,
        mainAxisExtent: cellExtent,
      ),
      children: [
        for (final s in EmergencyService.values)
          SgServiceCard(
            key: Key('service_card_${s.name}'),
            icon: s.icon,
            label: context.tr(s.labelKey),
            selected: selected == s,
            onTap: () => onSelect(s),
          ),
      ],
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
              topPad + 10,
              SgSpace.page,
              14,
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
                const SizedBox(height: 16),
                Text(
                  greeting,
                  style: SgType.caption.copyWith(
                    color: Colors.white,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 5),
                ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 250),
                  child: Text(
                    headline,
                    style: const TextStyle(
                      fontSize: 28,
                      height: 34 / 28,
                      fontWeight: FontWeight.w700,
                      color: Colors.white,
                      letterSpacing: -0.6,
                    ),
                  ),
                ),
                const SizedBox(height: 14),
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
        final (title, sub) = switch (r) {
          LocationReadiness.ready => (
            context.tr('home.location_ready'),
            context.tr('home.location_ready_hint'),
          ),
          LocationReadiness.servicesOff => (
            context.tr('home.location_off'),
            context.tr('home.location_off_hint'),
          ),
          LocationReadiness.permissionBlocked => (
            context.tr('home.location_blocked'),
            context.tr('home.location_off_hint'),
          ),
          LocationReadiness.permissionRequired => (
            context.tr('home.location_permission'),
            context.tr('home.location_off_hint'),
          ),
          LocationReadiness.unknown => (
            context.tr('home.location_finding'),
            context.tr('home.location_finding_hint'),
          ),
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
                      sub,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w400,
                        color: Colors.white.withValues(alpha: 0.82),
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
        // The hero pill already reports a healthy location state; only surface a
        // second card down here when the citizen must act (permission / GPS off).
        if (r == LocationReadiness.ready || r == LocationReadiness.unknown) {
          return const SizedBox.shrink();
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
        return Padding(
          padding: const EdgeInsets.only(top: 18),
          child: SgLocationCard(
            title: title,
            state: state,
            actionLabel: action,
            onAction: cb,
          ),
        );
      },
    );
  }
}
