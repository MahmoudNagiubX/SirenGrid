import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import '../../core/location.dart';
import '../../design/components/sg_buttons.dart';
import '../../design/components/sg_cards.dart';
import '../../design/components/sg_forms.dart';
import '../../design/tokens.dart';
import '../../l10n/strings.dart';
import '../../notifications/notification_coordinator.dart';
import '../auth/auth_cubit.dart';
import '../emergency/location_cubit.dart';

/// Screen 3 — Account Overview (brief §15). Read-only identity + permission
/// state + sign out. Registered address is shown as account context — never
/// used as an emergency location. No payments / medical history / edit ID.
class AccountScreen extends StatelessWidget {
  const AccountScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final profile = context.watch<AuthCubit>().state.profile;

    return Scaffold(
      key: const Key('account_screen'),
      backgroundColor: SgColors.bgApp,
      body: SafeArea(
        child: profile == null
            ? const SizedBox.shrink()
            : ListView(
                padding: const EdgeInsets.fromLTRB(
                  SgSpace.page,
                  14,
                  SgSpace.page,
                  120,
                ),
                children: [
                  const SizedBox(height: 4),
                  Text(
                    context.tr('account.title'),
                    style: SgType.title.copyWith(color: SgColors.textPrimary),
                  ),
                  const SizedBox(height: 20),
                  SgProfileCard(
                    name: profile.displayName,
                    initials: profile.initials,
                    verifiedLabel: context.tr('account.verified'),
                    fields: [
                      (
                        label: context.tr('account.phone'),
                        value: profile.phone,
                      ),
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
                    ],
                  ),
                  const SizedBox(height: 20),
                  _AddressCard(address: profile.registeredAddress),
                  const SizedBox(height: 20),
                  Text(
                    context.tr('account.permissions').toUpperCase(),
                    style: const TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: SgColors.textMuted,
                      letterSpacing: 0.4,
                    ),
                  ),
                  const SizedBox(height: 4),
                  _PermissionRows(),
                  const SizedBox(height: 24),
                  _SignOutButton(),
                ],
              ),
      ),
    );
  }
}

class _AddressCard extends StatelessWidget {
  const _AddressCard({required this.address});
  final String address;
  @override
  Widget build(BuildContext context) => SgInfoCard(
    icon: 'house',
    title: context.tr('account.address'),
    description: address,
  );
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
