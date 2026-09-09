import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import '../../core/location.dart';
import '../../design/components/sg_buttons.dart';
import '../../design/components/sg_forms.dart';
import '../../design/sg_icon.dart';
import '../../design/tokens.dart';
import '../../l10n/strings.dart';
import 'auth_cubit.dart';

/// Auth-flow screen (not a tab): create a synthetic-identity citizen account on
/// top of the existing phone + PIN system. A form, so it may scroll. On success
/// the [AuthCubit] issues a session and this route pops back to the auth gate,
/// which then shows the authenticated shell.
class RegisterScreen extends StatefulWidget {
  const RegisterScreen({super.key, this.locationService});

  /// Injectable for tests; production uses the default device GPS port.
  final LocationService? locationService;

  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

enum _LocState { idle, capturing, saved, failed }

class _RegisterScreenState extends State<RegisterScreen> {
  final _name = TextEditingController();
  final _phone = TextEditingController();
  final _nid = TextEditingController();
  final _pin = TextEditingController();
  final _pinConfirm = TextEditingController();
  final _address = TextEditingController();

  late final LocationService _location =
      widget.locationService ?? LocationService();

  _LocState _locState = _LocState.idle;
  double? _lat;
  double? _lon;

  // Field-level client errors, mirrored from the backend contract.
  String? _nameErr;
  String? _phoneErr;
  String? _nidErr;
  String? _pinErr;
  String? _pinConfirmErr;
  String? _addressErr;

  @override
  void dispose() {
    for (final c in [_name, _phone, _nid, _pin, _pinConfirm, _address]) {
      c.dispose();
    }
    super.dispose();
  }

  String _digits(String s) => s.replaceAll(RegExp(r'\D'), '');

  bool _validate() {
    final name = _name.text.trim();
    final phone = _digits(_phone.text);
    final nid = _digits(_nid.text);
    final pin = _pin.text;
    final pinConfirm = _pinConfirm.text;
    final address = _address.text.trim();

    setState(() {
      _nameErr = name.isEmpty ? context.tr('register.err_name') : null;
      _phoneErr = RegExp(r'^01\d{9}$').hasMatch(phone)
          ? null
          : context.tr('register.err_phone');
      _nidErr = RegExp(r'^\d{14}$').hasMatch(nid)
          ? null
          : context.tr('register.err_nid');
      _pinErr = RegExp(r'^\d{4,8}$').hasMatch(pin)
          ? null
          : context.tr('register.err_pin');
      _pinConfirmErr = pin == pinConfirm
          ? null
          : context.tr('register.err_pin_mismatch');
      _addressErr = address.length < 3
          ? context.tr('register.err_address')
          : null;
    });

    return [
      _nameErr,
      _phoneErr,
      _nidErr,
      _pinErr,
      _pinConfirmErr,
      _addressErr,
    ].every((e) => e == null);
  }

  Future<void> _useCurrentLocation() async {
    setState(() => _locState = _LocState.capturing);
    try {
      final pos = await _location.freshPosition();
      if (!mounted) return;
      setState(() {
        _lat = pos.latitude;
        _lon = pos.longitude;
        _locState = _LocState.saved;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _lat = null;
        _lon = null;
        _locState = _LocState.failed;
      });
    }
  }

  void _submit(bool busy) {
    if (busy) return;
    FocusScope.of(context).unfocus();
    if (!_validate()) return;
    final body = <String, dynamic>{
      'display_name': _name.text.trim(),
      'phone': _digits(_phone.text),
      'national_id': _digits(_nid.text),
      'pin': _pin.text,
      'pin_confirm': _pinConfirm.text,
      'registered_address_text': _address.text.trim(),
      if (_lat != null && _lon != null) ...{
        'registered_latitude': _lat,
        'registered_longitude': _lon,
      },
    };
    context.read<AuthCubit>().register(body);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      key: const Key('register_screen'),
      backgroundColor: SgColors.bgApp,
      body: SafeArea(
        child: BlocConsumer<AuthCubit, AuthState>(
          listenWhen: (_, s) => s is Authenticated,
          listener: (context, state) {
            if (state is Authenticated && Navigator.of(context).canPop()) {
              Navigator.of(context).pop();
            }
          },
          builder: (context, state) {
            final busy = state is AuthInProgress;
            final failure = state is AuthFailure && state.loginFailure
                ? state.message
                : null;
            final bannerErr = failure == null
                ? null
                : (failure.contains('.') && !failure.contains(' ')
                      ? context.tr(failure)
                      : failure);

            return Column(
              children: [
                _TopBar(
                  onBack: busy ? null : () => Navigator.of(context).pop(),
                ),
                Expanded(
                  child: SingleChildScrollView(
                    padding: const EdgeInsets.fromLTRB(26, 8, 26, 28),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Text(
                          context.tr('register.title'),
                          style: SgType.title.copyWith(
                            color: SgColors.textPrimary,
                          ),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          context.tr('register.subtitle'),
                          style: SgType.caption.copyWith(
                            color: SgColors.textMuted,
                          ),
                        ),
                        const SizedBox(height: 22),
                        if (bannerErr != null) ...[
                          _ErrorBanner(bannerErr),
                          const SizedBox(height: 16),
                        ],
                        SgTextField(
                          label: context.tr('register.name'),
                          controller: _name,
                          icon: 'user-round',
                          hint: context.tr('register.name_hint'),
                          textInputAction: TextInputAction.next,
                          autofillHints: const [AutofillHints.name],
                          error: _nameErr,
                        ),
                        const SizedBox(height: 14),
                        SgTextField(
                          label: context.tr('register.phone'),
                          controller: _phone,
                          icon: 'phone',
                          hint: context.tr('register.phone_hint'),
                          keyboardType: TextInputType.phone,
                          textInputAction: TextInputAction.next,
                          inputFormatters: [
                            FilteringTextInputFormatter.digitsOnly,
                            LengthLimitingTextInputFormatter(11),
                          ],
                          autofillHints: const [AutofillHints.telephoneNumber],
                          error: _phoneErr,
                        ),
                        const SizedBox(height: 14),
                        SgTextField(
                          label: context.tr('register.nid'),
                          controller: _nid,
                          icon: 'shield',
                          hint: context.tr('register.nid_hint'),
                          keyboardType: TextInputType.number,
                          textInputAction: TextInputAction.next,
                          inputFormatters: [
                            FilteringTextInputFormatter.digitsOnly,
                            LengthLimitingTextInputFormatter(14),
                          ],
                          error: _nidErr,
                        ),
                        const SizedBox(height: 14),
                        SgTextField(
                          label: context.tr('register.pin'),
                          controller: _pin,
                          icon: 'shield',
                          hint: context.tr('register.pin_hint'),
                          obscure: true,
                          keyboardType: TextInputType.number,
                          textInputAction: TextInputAction.next,
                          inputFormatters: [
                            FilteringTextInputFormatter.digitsOnly,
                            LengthLimitingTextInputFormatter(8),
                          ],
                          error: _pinErr,
                        ),
                        const SizedBox(height: 14),
                        SgTextField(
                          label: context.tr('register.pin_confirm'),
                          controller: _pinConfirm,
                          icon: 'shield',
                          hint: context.tr('register.pin_hint'),
                          obscure: true,
                          keyboardType: TextInputType.number,
                          textInputAction: TextInputAction.next,
                          inputFormatters: [
                            FilteringTextInputFormatter.digitsOnly,
                            LengthLimitingTextInputFormatter(8),
                          ],
                          error: _pinConfirmErr,
                        ),
                        const SizedBox(height: 14),
                        SgTextField(
                          label: context.tr('register.address'),
                          controller: _address,
                          icon: 'house',
                          hint: context.tr('register.address_hint'),
                          textInputAction: TextInputAction.done,
                          autofillHints: const [
                            AutofillHints.fullStreetAddress,
                          ],
                          error: _addressErr,
                        ),
                        const SizedBox(height: 10),
                        _LocationPicker(
                          state: _locState,
                          onTap: _locState == _LocState.capturing
                              ? null
                              : _useCurrentLocation,
                        ),
                        const SizedBox(height: 8),
                        Text(
                          context.tr('register.address_note'),
                          style: const TextStyle(
                            fontSize: 11,
                            color: SgColors.textMuted,
                            height: 1.4,
                          ),
                        ),
                        const SizedBox(height: 24),
                        SgPrimaryButton(
                          key: const Key('register_submit'),
                          label: context.tr('register.submit'),
                          full: true,
                          size: SgButtonSize.lg,
                          loading: busy,
                          onPressed: busy ? null : () => _submit(busy),
                        ),
                        const SizedBox(height: 14),
                        Center(
                          child: GestureDetector(
                            onTap: busy
                                ? null
                                : () => Navigator.of(context).pop(),
                            child: Text.rich(
                              TextSpan(
                                text: '${context.tr('register.have_account')} ',
                                style: SgType.caption.copyWith(
                                  color: SgColors.textMuted,
                                ),
                                children: [
                                  TextSpan(
                                    text: context.tr('register.login_link'),
                                    style: SgType.caption.copyWith(
                                      color: SgColors.infoStrong,
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}

class _TopBar extends StatelessWidget {
  const _TopBar({required this.onBack});
  final VoidCallback? onBack;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(14, 10, 14, 4),
      child: Row(
        children: [
          Semantics(
            button: true,
            label: MaterialLocalizations.of(context).backButtonTooltip,
            child: GestureDetector(
              onTap: onBack,
              behavior: HitTestBehavior.opaque,
              child: Container(
                width: 44,
                height: 44,
                alignment: Alignment.center,
                child: const SgIcon(
                  'arrow-left',
                  size: 22,
                  color: SgColors.textPrimary,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _LocationPicker extends StatelessWidget {
  const _LocationPicker({required this.state, required this.onTap});
  final _LocState state;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final (icon, label, tone) = switch (state) {
      _LocState.saved => (
        'map-pin',
        context.tr('register.location_saved'),
        SgColors.infoStrong,
      ),
      _LocState.capturing => (
        'navigation',
        context.tr('register.location_capturing'),
        SgColors.textMuted,
      ),
      _LocState.failed => (
        'refresh-cw',
        context.tr('register.location_failed'),
        SgColors.emergencyHover,
      ),
      _LocState.idle => (
        'navigation',
        context.tr('register.use_location'),
        SgColors.textPrimary,
      ),
    };
    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        decoration: BoxDecoration(
          color: SgColors.bgSurface,
          borderRadius: BorderRadius.circular(SgRadius.control),
          border: Border.all(
            color: state == _LocState.saved
                ? SgColors.infoStrong
                : SgColors.borderHairline,
            width: 1.5,
          ),
        ),
        child: Row(
          children: [
            if (state == _LocState.capturing)
              const SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: SgColors.textMuted,
                ),
              )
            else
              SgIcon(icon, size: 18, color: tone),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                label,
                style: SgType.bodyMedium.copyWith(
                  color: tone,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
            if (state == _LocState.saved)
              const SgIcon(
                'shield-check',
                size: 16,
                color: SgColors.infoStrong,
              ),
          ],
        ),
      ),
    );
  }
}

class _ErrorBanner extends StatelessWidget {
  const _ErrorBanner(this.message);
  final String message;
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: SgColors.emergencySoft,
        borderRadius: BorderRadius.circular(SgRadius.control),
        border: Border.all(color: SgColors.emergencyBorder),
      ),
      child: Row(
        children: [
          const SgIcon('shield', size: 18, color: SgColors.emergencyHover),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              message,
              style: SgType.caption.copyWith(color: SgColors.emergencyHover),
            ),
          ),
        ],
      ),
    );
  }
}
