import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import '../../design/components/sg_buttons.dart';
import '../../design/components/sg_forms.dart';
import '../../design/sg_icon.dart';
import '../../design/tokens.dart';
import '../../l10n/strings.dart';
import 'auth_cubit.dart';
import 'register_screen.dart';

/// Screen 0 — Login (brief §15). Phone + PIN only. No registration / OTP /
/// social / National ID / forgot-password. Renders loading, invalid-credentials
/// and network-failure states; a success transitions via the auth gate.
class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _phone = TextEditingController();
  final _pin = TextEditingController();

  @override
  void dispose() {
    _phone.dispose();
    _pin.dispose();
    super.dispose();
  }

  void _submit() {
    FocusScope.of(context).unfocus();
    context.read<AuthCubit>().login(_phone.text, _pin.text);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      key: const Key('login_screen'),
      backgroundColor: SgColors.bgApp,
      body: SafeArea(
        child: BlocBuilder<AuthCubit, AuthState>(
          builder: (context, state) {
            final busy = state is AuthInProgress;
            final failure = state is AuthFailure && state.loginFailure
                ? state.message
                : null;
            // Field-vs-generic error routing.
            final isPinErr = failure == 'login.err_pin';
            final isRequiredErr = failure == 'login.err_required';
            final bannerErr = failure != null && !isPinErr && !isRequiredErr
                ? _resolve(context, failure)
                : null;

            return LayoutBuilder(
              builder: (context, constraints) => SingleChildScrollView(
                child: ConstrainedBox(
                  constraints: BoxConstraints(minHeight: constraints.maxHeight),
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(26, 20, 26, 24),
                    child: IntrinsicHeight(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          const SizedBox(height: 20),
                          const _AmbulanceMark(width: 190),
                          const SizedBox(height: 18),
                          Text(
                            context.tr('app.name'),
                            textAlign: TextAlign.center,
                            style: SgType.title.copyWith(
                              color: SgColors.textPrimary,
                            ),
                          ),
                          const SizedBox(height: 6),
                          Text(
                            context.tr('login.tagline'),
                            textAlign: TextAlign.center,
                            style: SgType.caption.copyWith(
                              color: SgColors.textMuted,
                            ),
                          ),
                          const SizedBox(height: 32),
                          if (bannerErr != null) ...[
                            _ErrorBanner(bannerErr),
                            const SizedBox(height: 16),
                          ],
                          SgTextField(
                            label: context.tr('login.phone'),
                            controller: _phone,
                            icon: 'phone',
                            hint: context.tr('login.phone_hint'),
                            keyboardType: TextInputType.phone,
                            textInputAction: TextInputAction.next,
                            autofillHints: const [
                              AutofillHints.telephoneNumber,
                            ],
                            error: isRequiredErr && _phone.text.trim().isEmpty
                                ? context.tr('login.err_required')
                                : null,
                          ),
                          const SizedBox(height: 16),
                          SgTextField(
                            label: context.tr('login.pin'),
                            controller: _pin,
                            icon: 'shield',
                            hint: context.tr('login.pin_hint'),
                            obscure: true,
                            keyboardType: TextInputType.number,
                            inputFormatters: [
                              FilteringTextInputFormatter.digitsOnly,
                              LengthLimitingTextInputFormatter(4),
                            ],
                            textInputAction: TextInputAction.done,
                            onSubmitted: (_) => _submit(),
                            error: isPinErr
                                ? context.tr('login.err_pin')
                                : null,
                          ),
                          // Fixed, calm gap before the CTA. The bare Spacer()
                          // here previously ate every pixel of slack on tall
                          // devices and left an awkward void under the PIN field.
                          const SizedBox(height: 40),
                          SgPrimaryButton(
                            label: context.tr('login.submit'),
                            full: true,
                            size: SgButtonSize.lg,
                            loading: busy,
                            onPressed: busy ? null : _submit,
                          ),
                          const SizedBox(height: 12),
                          _CreateAccountLink(enabled: !busy),
                          const SizedBox(height: 12),
                          Text(
                            context.tr('login.demo_note'),
                            textAlign: TextAlign.center,
                            style: const TextStyle(
                              fontSize: 11,
                              color: SgColors.textMuted,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            );
          },
        ),
      ),
    );
  }

  static String _resolve(BuildContext context, String key) =>
      key.contains('.') ? context.tr(key) : key;
}

class _CreateAccountLink extends StatelessWidget {
  const _CreateAccountLink({required this.enabled});
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: GestureDetector(
        onTap: enabled
            ? () => Navigator.of(context).push(
                MaterialPageRoute<void>(builder: (_) => const RegisterScreen()),
              )
            : null,
        behavior: HitTestBehavior.opaque,
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 6),
          child: Text.rich(
            TextSpan(
              text: '${context.tr('login.no_account')} ',
              style: SgType.caption.copyWith(color: SgColors.textMuted),
              children: [
                TextSpan(
                  text: context.tr('login.create_account'),
                  style: SgType.caption.copyWith(
                    color: SgColors.infoStrong,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
            ),
          ),
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

/// A compact flat-vector ambulance mark (brief §12 — original geometry, not a
/// copy of any reference). White body, navy windows, red cross, soft ground
/// shadow, translucent red/navy backdrop blob.
class _AmbulanceMark extends StatelessWidget {
  const _AmbulanceMark({this.width = 190});
  final double width;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: width,
      height: width * 0.62,
      child: CustomPaint(painter: _AmbulancePainter()),
    );
  }
}

class _AmbulancePainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width;
    final h = size.height;
    final s = w / 300;

    // backdrop blob
    canvas.drawOval(
      Rect.fromCenter(
        center: Offset(w * 0.52, h * 0.42),
        width: w * 0.96,
        height: h * 0.9,
      ),
      Paint()..color = SgColors.emergency.withValues(alpha: 0.10),
    );
    canvas.drawOval(
      Rect.fromCenter(
        center: Offset(w * 0.30, h * 0.30),
        width: w * 0.5,
        height: h * 0.5,
      ),
      Paint()..color = SgColors.navy900.withValues(alpha: 0.07),
    );

    // ground shadow
    canvas.drawOval(
      Rect.fromCenter(
        center: Offset(w * 0.5, h * 0.9),
        width: w * 0.7,
        height: 16 * s,
      ),
      Paint()..color = SgColors.navy950.withValues(alpha: 0.12),
    );

    final body = Paint()..color = Colors.white;
    final stroke = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3 * s
      ..color = SgColors.navy900;

    // van body
    final bodyRect = RRect.fromRectAndRadius(
      Rect.fromLTWH(w * 0.10, h * 0.34, w * 0.62, h * 0.40),
      Radius.circular(14 * s),
    );
    // cab
    final cabRect = RRect.fromRectAndRadius(
      Rect.fromLTWH(w * 0.62, h * 0.44, w * 0.24, h * 0.30),
      Radius.circular(12 * s),
    );
    canvas.drawRRect(bodyRect, body);
    canvas.drawRRect(cabRect, body);
    canvas.drawRRect(bodyRect, stroke);
    canvas.drawRRect(cabRect, stroke);

    // red side stripe
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        Rect.fromLTWH(w * 0.10, h * 0.55, w * 0.62, h * 0.06),
        Radius.circular(4 * s),
      ),
      Paint()..color = SgColors.emergency,
    );

    // window (navy)
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        Rect.fromLTWH(w * 0.66, h * 0.48, w * 0.16, h * 0.13),
        Radius.circular(6 * s),
      ),
      Paint()..color = SgColors.navy900,
    );

    // medical cross
    final cx = w * 0.30, cy = h * 0.46;
    final cross = Paint()..color = SgColors.emergency;
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        Rect.fromCenter(center: Offset(cx, cy), width: 10 * s, height: 28 * s),
        Radius.circular(2 * s),
      ),
      cross,
    );
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        Rect.fromCenter(center: Offset(cx, cy), width: 28 * s, height: 10 * s),
        Radius.circular(2 * s),
      ),
      cross,
    );

    // wheels
    final wheel = Paint()..color = SgColors.navy900;
    final hub = Paint()..color = Colors.white;
    for (final wx in [w * 0.26, w * 0.70]) {
      canvas.drawCircle(Offset(wx, h * 0.76), 13 * s, wheel);
      canvas.drawCircle(Offset(wx, h * 0.76), 5 * s, hub);
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
