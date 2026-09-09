import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import '../../core/location.dart';
import '../../design/components/sg_buttons.dart';
import '../../design/components/sg_forms.dart';
import '../../design/sg_icon.dart';
import '../../design/tokens.dart';
import '../../l10n/strings.dart';
import '../../notifications/notification_coordinator.dart';
import '../auth/auth_cubit.dart';
import '../auth/citizen_profile.dart';
import '../emergency/location_cubit.dart';

/// Screen 3 — Account Overview (brief §15). Read-only identity + permission
/// state + sign out. A navy SirenGrid identity band over the Light Mist content
/// gives it the same intentional feel as Home without going red-heavy.
/// Registered address is account context — never an emergency location. No
/// payments / medical history / edit ID. Every value comes from `GET /me`.
class AccountScreen extends StatelessWidget {
  const AccountScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final profile = context.watch<AuthCubit>().state.profile;
    if (profile == null) return const SizedBox.shrink();

    return Scaffold(
      key: const Key('account_screen'),
      backgroundColor: SgColors.bgApp,
      body: Column(
        children: [
          _IdentityHeader(profile: profile),
          Expanded(
            child: ListView(
              padding: const EdgeInsets.fromLTRB(
                SgSpace.page,
                20,
                SgSpace.page,
                28,
              ),
              children: [
                _SectionLabel(context.tr('account.identity_section')),
                const SizedBox(height: 10),
                _IdentityDetails(profile: profile),
                const SizedBox(height: 22),
                _SectionLabel(context.tr('account.address')),
                const SizedBox(height: 10),
                _AddressCard(address: profile.registeredAddress),
                const SizedBox(height: 22),
                _SectionLabel(context.tr('account.permissions')),
                const SizedBox(height: 4),
                _PermissionRows(),
                const SizedBox(height: 24),
                _SignOutButton(),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _IdentityHeader extends StatelessWidget {
  const _IdentityHeader({required this.profile});
  final CitizenProfile profile;

  @override
  Widget build(BuildContext context) {
    final topPad = MediaQuery.of(context).padding.top;
    return Container(
      decoration: const BoxDecoration(
        color: SgColors.navy900,
        borderRadius: BorderRadius.vertical(bottom: Radius.circular(28)),
        boxShadow: SgShadows.card,
      ),
      child: Stack(
        children: [
          // soft light bloom, mirroring the Home hero
          Positioned(
            right: -60,
            top: -50,
            child: Container(
              width: 200,
              height: 200,
              decoration: const BoxDecoration(
                shape: BoxShape.circle,
                gradient: RadialGradient(
                  colors: [Color(0x1FFFFFFF), Color(0x00FFFFFF)],
                  stops: [0, 0.7],
                ),
              ),
            ),
          ),
          // thin SirenGrid-red accent along the bottom edge
          Positioned(
            left: 24,
            right: 24,
            bottom: 0,
            child: Container(
              height: 3,
              decoration: BoxDecoration(
                color: SgColors.emergency,
                borderRadius: BorderRadius.circular(SgRadius.pill),
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
                Text(
                  context.tr('account.title'),
                  style: SgType.caption.copyWith(
                    color: Colors.white.withValues(alpha: 0.7),
                    fontWeight: FontWeight.w600,
                    letterSpacing: 0.4,
                  ),
                ),
                const SizedBox(height: 16),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                    Container(
                      width: 58,
                      height: 58,
                      decoration: BoxDecoration(
                        color: Colors.white,
                        shape: BoxShape.circle,
                        border: Border.all(
                          color: Colors.white.withValues(alpha: 0.5),
                          width: 2,
                        ),
                      ),
                      alignment: Alignment.center,
                      child: Text(
                        profile.initials,
                        style: SgType.cardHeading.copyWith(
                          color: SgColors.navy900,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            profile.displayName,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: SgType.title.copyWith(color: Colors.white),
                          ),
                          const SizedBox(height: 6),
                          _VerifiedChip(label: context.tr('account.verified')),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                Row(
                  children: [
                    SgIcon(
                      'route',
                      size: 13,
                      color: Colors.white.withValues(alpha: 0.55),
                    ),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Text(
                        profile.citizenReference,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: SgType.caption.copyWith(
                          color: Colors.white.withValues(alpha: 0.62),
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _VerifiedChip extends StatelessWidget {
  const _VerifiedChip({required this.label});
  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: SgColors.blue200.withValues(alpha: 0.22),
        borderRadius: BorderRadius.circular(SgRadius.pill),
        border: Border.all(color: SgColors.blue200.withValues(alpha: 0.5)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          const SgIcon('shield-check', size: 13, color: SgColors.blue200),
          const SizedBox(width: 5),
          Text(
            label,
            style: SgType.chip.copyWith(
              color: SgColors.blue100,
              letterSpacing: 0.2,
            ),
          ),
        ],
      ),
    );
  }
}

class _SectionLabel extends StatelessWidget {
  const _SectionLabel(this.text);
  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(
      text.toUpperCase(),
      style: const TextStyle(
        fontSize: 12,
        fontWeight: FontWeight.w700,
        color: SgColors.textMuted,
        letterSpacing: 0.6,
      ),
    );
  }
}

class _IdentityDetails extends StatelessWidget {
  const _IdentityDetails({required this.profile});
  final CitizenProfile profile;

  @override
  Widget build(BuildContext context) {
    final rows = <({String label, String value})>[
      (label: context.tr('account.phone'), value: profile.phone),
      (
        label: context.tr('account.national_id'),
        value: profile.nationalIdMasked,
      ),
      (
        label: context.tr('account.citizen_ref'),
        value: profile.citizenReference,
      ),
      (
        label: context.tr('account.identity_status'),
        value: profile.identityStatusLabel,
      ),
    ];
    return Container(
      decoration: BoxDecoration(
        color: SgColors.bgSurface,
        borderRadius: BorderRadius.circular(SgRadius.cardLg),
        border: Border.all(color: SgColors.borderHairline),
        boxShadow: SgShadows.card,
      ),
      child: Column(
        children: [
          for (var i = 0; i < rows.length; i++)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 15),
              decoration: BoxDecoration(
                border: i == rows.length - 1
                    ? null
                    : const Border(
                        bottom: BorderSide(color: SgColors.borderHairline),
                      ),
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SizedBox(
                    width: 118,
                    child: Text(
                      rows[i].label,
                      style: SgType.caption.copyWith(color: SgColors.textMuted),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      rows[i].value,
                      textAlign: TextAlign.end,
                      style: SgType.bodyMedium.copyWith(
                        color: SgColors.textPrimary,
                        fontWeight: FontWeight.w600,
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

class _AddressCard extends StatelessWidget {
  const _AddressCard({required this.address});
  final String address;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: SgColors.bgSurface,
        borderRadius: BorderRadius.circular(SgRadius.cardLg),
        border: Border.all(color: SgColors.borderHairline),
        boxShadow: SgShadows.card,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 42,
            height: 42,
            decoration: BoxDecoration(
              color: SgColors.infoSoft,
              borderRadius: BorderRadius.circular(SgRadius.control),
            ),
            child: const Center(
              child: SgIcon('house', size: 20, color: SgColors.infoStrong),
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  address,
                  style: SgType.bodyMedium.copyWith(
                    color: SgColors.textPrimary,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  context.tr('account.address_note'),
                  style: SgType.caption.copyWith(color: SgColors.textMuted),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _PermissionRows extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        BlocBuilder<LocationCubit, LocationReadiness>(
          builder: (context, r) => SgPermissionRow(
            icon: 'map-pin',
            label: context.tr('account.perm_location'),
            description: context.tr('account.perm_location_desc'),
            granted: r == LocationReadiness.ready,
            grantedLabel: context.tr('account.granted'),
            actionLabel: context.tr('account.allow'),
            onAction: () => context.read<LocationCubit>().requestPermission(),
          ),
        ),
        BlocBuilder<NotificationCoordinator, NotificationPermissionState>(
          builder: (context, p) => SgPermissionRow(
            icon: 'bell',
            label: context.tr('account.perm_notifications'),
            description: context.tr('account.perm_notifications_desc'),
            granted: p == NotificationPermissionState.authorized,
            grantedLabel: context.tr('account.granted'),
            actionLabel: context.tr('account.allow'),
            onAction: () =>
                context.read<NotificationCoordinator>().requestPermission(),
          ),
        ),
      ],
    );
  }
}

class _SignOutButton extends StatefulWidget {
  @override
  State<_SignOutButton> createState() => _SignOutButtonState();
}

class _SignOutButtonState extends State<_SignOutButton> {
  bool _busy = false;

  @override
  Widget build(BuildContext context) {
    return SgSecondaryButton(
      label: context.tr('account.signout'),
      icon: 'log-out',
      full: true,
      onPressed: _busy
          ? null
          : () async {
              setState(() => _busy = true);
              await context.read<AuthCubit>().logout();
            },
    );
  }
}
